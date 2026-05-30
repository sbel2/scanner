from __future__ import annotations

import sys
import traceback
from datetime import date

from . import db, emailer
from .config import DB_PATH, DRY_RUN, MIN_SCORE_TO_SEND, TOP_N
from .eligibility import check as check_eligibility
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

    try:
        collected = collect_all()
        print(f"[scanner] collected {len(collected)} raw items")

        with db.connect(DB_PATH) as conn:
            new = [o for o in collected if db.is_new_or_updated(conn, o)]
            for o in new:
                db.mark_seen(conn, o)
        print(f"[scanner] {len(new)} new/updated after dedupe")

        if not new:
            print("[scanner] nothing new to score; ending without sending")
        else:
            scorer = AlignmentScorer()
            scored: list[ScoredOpportunity] = []
            for opp in new:
                verdict = check_eligibility(opp)
                if verdict.eligible == "no":
                    print(f"  drop (ineligible): {opp.title[:80]}  — {verdict.reason}")
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
            eligible = [s for s in ranked if s.final_score >= MIN_SCORE_TO_SEND]
            top = eligible[:TOP_N]

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
                        db.record_digest(conn, sent_ids, subject)
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
