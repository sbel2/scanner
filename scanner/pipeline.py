from __future__ import annotations

import sys
import traceback

from . import db, emailer
from .config import (
    DB_PATH,
    DRY_RUN,
    ENRICH_CANDIDATES,
    MIN_SCORE_TO_SEND,
    NEWS_MAX,
    TOP_N,
)
from .eligibility import rule_based_reject
from .enrich import vet
from .filters import is_expired, prefilter
from .models import ScoredOpportunity
from .prerank import prerank
from .ranker import rank
from .scoring import AlignmentScorer
from .sources import collect_all


def run(welcome: bool = False) -> int:
    db.init_db(DB_PATH)
    print(f"[scanner] starting run · dry_run={DRY_RUN} · top_n={TOP_N} · welcome={welcome}")

    with db.connect(DB_PATH) as conn:
        run_id = db.start_run(conn)

    error: str | None = None
    collected: list = []
    new: list = []
    eligible: list[ScoredOpportunity] = []
    sent_ids: list[str] = []
    # Opportunities that reached a terminal decision this run and are therefore
    # safe to remember. We commit these only AFTER a successful send, so a
    # failure (bad token, rate limit, Resend outage) doesn't burn the day's
    # items — they stay "new" and get retried on the next run. Transient
    # scoring failures are deliberately left out so they retry too.
    to_mark_seen: list = []

    try:
        collected = collect_all()
        print(f"[scanner] collected {len(collected)} raw items")

        # Universal pre-filter: drop repost/social domains and collapse the same
        # event scraped under many URLs/titles down to one canonical variant.
        collected, n_blocked, n_deduped = prefilter(collected)
        print(
            f"[scanner] {len(collected)} after prefilter "
            f"(dropped {n_blocked} repost-domain, {n_deduped} duplicate)"
        )

        with db.connect(DB_PATH) as conn:
            new = [o for o in collected if db.is_new_or_updated(conn, o)]
        print(f"[scanner] {len(new)} new/updated after dedupe")

        if not new:
            print("[scanner] nothing new to score; ending without sending")
        else:
            # --- Cheap deterministic + regex gates first (no LLM, no fetch) ----
            # Drop items that already carry a past date (mostly calendar/watch
            # feeds) and obvious hard-reject regex matches before we spend a page
            # read on anything.
            survivors: list = []
            for opp in new:
                expired, why = is_expired(opp)
                if expired:
                    print(f"  drop (expired): {opp.title[:80]}  — {why}")
                    to_mark_seen.append(opp)
                    continue
                rejected, reason = rule_based_reject(opp)
                if rejected:
                    print(f"  drop (hard-reject): {opp.title[:80]}  — {reason}")
                    to_mark_seen.append(opp)
                    continue
                survivors.append(opp)

            # --- Pick the most promising slice to read pages for ---------------
            # Reading a page is the accurate-but-costly step, so we only do it for
            # the top candidates (enough to fill the digest with headroom) rather
            # than all ~150 items. Items not chosen are left unmarked so they get
            # another shot on a future run.
            candidates = prerank(survivors, ENRICH_CANDIDATES)
            print(
                f"[scanner] {len(survivors)} survived cheap gates; "
                f"reading pages for top {len(candidates)}"
            )

            # --- Enrich + vet on the REAL page, then score ---------------------
            # One page read per candidate fills its real date/location/audience
            # AND decides freshness + eligibility. Everything is judged on facts,
            # not the search snippet. Unreadable pages are dropped (we can't
            # verify them) and left unmarked so a later run can retry.
            scorer = AlignmentScorer()
            scored: list[ScoredOpportunity] = []
            for opp in candidates:
                result = vet(opp)
                if not result.readable:
                    print(f"  drop (unreadable): {opp.title[:80]}  — page could not be read")
                    continue

                enriched = result.opp
                expired, why = is_expired(enriched)  # backstop on freshly-read dates
                if result.expired or expired:
                    print(
                        f"  drop (expired on page): {enriched.title[:80]}  "
                        f"— {why or result.expired_reason}"
                    )
                    to_mark_seen.append(opp)
                    continue
                if result.verdict.eligible == "no":
                    print(f"  drop (ineligible): {enriched.title[:80]}  — {result.verdict.reason}")
                    to_mark_seen.append(opp)
                    continue

                alignment = scorer.score(enriched)
                scored.append(
                    ScoredOpportunity(
                        opportunity=enriched, eligibility=result.verdict, alignment=alignment
                    )
                )
                print(
                    f"  scored {alignment.score:.1f}: {enriched.title[:80]}"
                    + (f"  [{result.verdict.eligible}]" if result.verdict.eligible != "yes" else "")
                )

            ranked = rank(scored)

            # Remember items that scored cleanly (regardless of whether they make
            # the cut). Items whose scoring transiently failed are left unmarked
            # so a fixed key / recovered rate limit lets them retry next run.
            for s in scored:
                if not s.alignment.reasoning.startswith("scoring failed:"):
                    to_mark_seen.append(s.opportunity)

            eligible = [s for s in ranked if s.final_score >= MIN_SCORE_TO_SEND]

            # Suppress anything already emailed in the last 7 days — both the
            # exact item (by id) and the same real-world opportunity reappearing
            # under a different URL/title (by normalized dedup key). We still
            # mark them seen above; we just don't re-spam them.
            with db.connect(DB_PATH) as conn:
                eligible = [
                    s for s in eligible
                    if not db.was_recently_in_digest(conn, s.opportunity.id)
                    and not db.was_key_recently_in_digest(conn, s.opportunity.dedup_key)
                ]

            # Opportunities fill TOP_N; news rides along in its own capped lane so
            # it can never push a real opportunity out of the digest.
            opp_picks = [s for s in eligible if s.opportunity.category != "news"][:TOP_N]
            news_picks = [s for s in eligible if s.opportunity.category == "news"][:NEWS_MAX]
            top = opp_picks + news_picks

            with db.connect(DB_PATH) as conn:
                for s in ranked:
                    db.upsert_opportunity(conn, s)

            print(
                f"[scanner] {len(ranked)} scored, {len(opp_picks)} opportunities "
                f"+ {len(news_picks)} news pass threshold"
            )

            failed = [s for s in scored if s.alignment.reasoning.startswith("scoring failed:")]
            scoring_broken = len(scored) > 0 and len(failed) / len(scored) >= 0.5

            if top:
                if DRY_RUN:
                    subject, html = emailer.render(top, total_new=len(new), welcome=welcome)
                    print(f"[scanner] DRY_RUN — would send: {subject}")
                    print(f"[scanner] DRY_RUN — html preview ({len(html)} chars)")
                else:
                    subject, sent_ids = emailer.send(top, total_new=len(new), welcome=welcome)
                    with db.connect(DB_PATH) as conn:
                        db.record_digest(
                            conn,
                            sent_ids,
                            subject,
                            dedup_keys=[s.opportunity.dedup_key for s in top],
                        )
                    print(f"[scanner] sent: {subject}")
            elif scoring_broken:
                print(f"[scanner] {len(failed)}/{len(scored)} scoring calls failed — sending alert")
                if not DRY_RUN:
                    emailer.send_failure_alert(
                        total_new=len(scored),
                        failed_scoring=len(failed),
                        sample_error=failed[0].alignment.reasoning,
                    )
            else:
                print("[scanner] nothing passed threshold; no email sent")

        # Commit seen-state only after the run has gotten this far without
        # raising. A dry run is non-destructive on purpose, so it never marks
        # items seen — you can preview repeatedly, then do the real send.
        if not DRY_RUN and to_mark_seen:
            with db.connect(DB_PATH) as conn:
                for o in to_mark_seen:
                    db.mark_seen(conn, o)

    except Exception:
        error = traceback.format_exc()
        print(f"[scanner] FAILED:\n{error}", file=sys.stderr)
        return 1
    finally:
        with db.connect(DB_PATH) as conn:
            db.finish_run(
                conn,
                run_id,
                collected=len(collected),
                new=len(new),
                eligible=len(eligible),
                sent=len(sent_ids),
                error=error,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
