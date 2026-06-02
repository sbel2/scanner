from __future__ import annotations

import sys
import traceback

from . import db, emailer
from .config import DB_PATH, DRY_RUN, MIN_SCORE_TO_SEND, TOP_N
from .eligibility import check as check_eligibility
from .filters import is_expired, prefilter
from .freshness import verify_fresh
from .models import ScoredOpportunity
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
            scorer = AlignmentScorer()
            scored: list[ScoredOpportunity] = []
            for opp in new:
                # Deterministic expiry gate — runs before any LLM call so a
                # closed deadline or past event date is dropped for free and
                # never reaches scoring.
                expired, why = is_expired(opp)
                if expired:
                    print(f"  drop (expired): {opp.title[:80]}  — {why}")
                    to_mark_seen.append(opp)
                    continue

                verdict = check_eligibility(opp)
                if verdict.eligible == "no":
                    print(f"  drop (ineligible): {opp.title[:80]}  — {verdict.reason}")
                    to_mark_seen.append(opp)  # deliberately rejected — don't re-evaluate
                    continue
                alignment = scorer.score(opp)
                scored.append(
                    ScoredOpportunity(
                        opportunity=opp, eligibility=verdict, alignment=alignment
                    )
                )
                print(
                    f"  scored {alignment.score:.1f}: {opp.title[:80]}"
                    + (f"  [{verdict.eligible}]" if verdict.eligible != "yes" else "")
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

            # Verify-before-send freshness gate. Snippet dates are unreliable and
            # often absent, so we read each candidate's actual page (in rank
            # order) and drop anything the page shows has already passed, filling
            # the digest with the next fresh item until we hit TOP_N. This is the
            # accurate-but-costly step, so it runs only on items that would ship.
            # Dropped items are already in to_mark_seen (they scored cleanly), so
            # they won't be re-fetched on future runs.
            top: list[ScoredOpportunity] = []
            for s in eligible:
                if len(top) >= TOP_N:
                    break
                expired, why = verify_fresh(s.opportunity)
                if expired:
                    print(f"  drop (expired on page): {s.opportunity.title[:80]}  — {why}")
                    continue
                top.append(s)

            with db.connect(DB_PATH) as conn:
                for s in ranked:
                    db.upsert_opportunity(conn, s)

            print(f"[scanner] {len(ranked)} scored, {len(top)} pass threshold + top_n")

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
