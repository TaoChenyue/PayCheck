"""Django management command: migrate legacy SQLite data to new Django ORM.

Usage:
    python manage.py migrate_legacy_db [--db-path <path>] [--dry-run]

Workflow:
    1. Read old SQLite database (log/paycheck.db)
    2. Export to JSON intermediate format
    3. Map platform: "bank" → "boc"
    4. Bulk create Transaction records via Django ORM
    5. Verify total count + total amount match
"""

import hashlib
import json
import os
import sqlite3
import sys
from typing import Dict, List, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from apps.transactions.models import Transaction


def _compute_row_hash(time_str, amount, counterparty, platform):
    """MD5 hash for dedup: time|amount|counterparty|platform"""
    raw = f"{time_str}|{amount:.2f}|{counterparty}|{platform}"
    return hashlib.md5(raw.encode()).hexdigest()


def read_legacy_db(db_path: str) -> Tuple[List[Dict], Dict]:
    """Read all transactions from legacy SQLite database.

    Returns:
        (transactions_list, summary_dict)
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Legacy database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, platform, time, category, counterparty, amount, tx_type,
               payment_method, description, balance, currency,
               branch, cp_account, cp_bank
        FROM transactions
        ORDER BY time ASC
    """).fetchall()

    # Read tags
    tag_rows = conn.execute(
        "SELECT id, name FROM tags ORDER BY id"
    ).fetchall()
    tag_map = {r["id"]: r["name"] for r in tag_rows}

    # Read transaction_tags
    tx_tag_rows = conn.execute(
        "SELECT transaction_id, tag_id FROM transaction_tags"
    ).fetchall()
    tx_tags: Dict[int, List[int]] = {}
    for r in tx_tag_rows:
        tx_tags.setdefault(r["transaction_id"], []).append(r["tag_id"])

    # Compute summary for verification
    summary_row = conn.execute("""
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN tx_type = '支出' THEN amount ELSE 0 END), 0) AS total_expense,
            COALESCE(SUM(CASE WHEN tx_type = '收入' THEN amount ELSE 0 END), 0) AS total_income
        FROM transactions
    """).fetchone()

    conn.close()

    transactions = []
    for r in rows:
        tx = dict(r)
        # Map platform: "bank" → "boc"
        if tx["platform"] == "bank":
            tx["platform"] = "boc"
        # Attach tag names
        tx["_tag_ids"] = tx_tags.get(tx["id"], [])
        tx["_tag_names"] = [tag_map.get(tid, "") for tid in tx["_tag_ids"]]
        transactions.append(tx)

    summary = {
        "total_count": summary_row["total_count"] or 0,
        "total_expense": round(summary_row["total_expense"] or 0, 2),
        "total_income": round(summary_row["total_income"] or 0, 2),
    }

    return transactions, summary


def migrate_to_django(transactions: List[Dict]) -> Dict:
    """Bulk-insert legacy transactions into Django ORM Transaction model.

    Uses bulk_create with batch_size=500 for performance.
    Skips records with duplicate row_hash.

    Returns:
        dict with created, skipped, errors counts
    """
    created = 0
    skipped = 0
    errors = 0
    batch = []
    seen_hashes = set(Transaction.objects.values_list("row_hash", flat=True))

    for tx in transactions:
        platform = tx["platform"]  # already mapped bank→boc
        row_hash = _compute_row_hash(
            tx["time"], tx["amount"], tx.get("counterparty", ""), platform
        )

        if row_hash in seen_hashes:
            skipped += 1
            continue

        seen_hashes.add(row_hash)

        batch.append(
            Transaction(
                platform=platform,
                time=tx["time"],
                category=tx.get("category", ""),
                counterparty=tx.get("counterparty", ""),
                description=tx.get("description", ""),
                amount=tx["amount"],
                tx_type=tx.get("tx_type", "支出"),
                payment_method=tx.get("payment_method", ""),
                balance=tx.get("balance", 0.0),
                currency=tx.get("currency", ""),
                branch=tx.get("branch", ""),
                cp_account=tx.get("cp_account", ""),
                cp_bank=tx.get("cp_bank", ""),
                source_channel=platform,
                source_id=0,  # legacy data has no channel table FK
                row_hash=row_hash,
            )
        )

        if len(batch) >= 500:
            try:
                Transaction.objects.bulk_create(batch, ignore_conflicts=True)
                created += len(batch)
            except Exception as e:
                errors += len(batch)
                sys.stderr.write(f"Bulk create error: {e}\n")
            batch = []

    # Final batch
    if batch:
        try:
            Transaction.objects.bulk_create(batch, ignore_conflicts=True)
            created += len(batch)
        except Exception as e:
            errors += len(batch)
            sys.stderr.write(f"Bulk create error: {e}\n")

    return {"created": created, "skipped": skipped, "errors": errors}


def verify_migration(legacy_summary: Dict) -> Dict:
    """Verify migrated data matches legacy summary.

    Compares total count and total amounts between old and new databases.
    """
    from django.db.models import Q, Sum

    txns = Transaction.objects.all()
    new_count = txns.count()
    new_expense = txns.filter(tx_type="支出").aggregate(s=Sum("amount"))["s"] or 0.0
    new_income = txns.filter(tx_type="收入").aggregate(s=Sum("amount"))["s"] or 0.0

    legacy_count = legacy_summary["total_count"]
    legacy_expense = legacy_summary["total_expense"]
    legacy_income = legacy_summary["total_income"]

    return {
        "count_match": new_count >= legacy_count,  # new may have more (fresh data)
        "expense_match": abs(new_expense - legacy_expense) < 0.02,
        "income_match": abs(new_income - legacy_income) < 0.02,
        "legacy": {
            "count": legacy_count,
            "expense": legacy_expense,
            "income": legacy_income,
        },
        "new": {
            "count": new_count,
            "expense": round(new_expense, 2),
            "income": round(new_income, 2),
        },
    }


class Command(BaseCommand):
    help = "Migrate legacy SQLite data to new Django ORM with platform mapping."

    def add_arguments(self, parser):
        parser.add_argument(
            "--db-path",
            default=None,
            help="Path to legacy SQLite database (default: <repo>/log/paycheck.db)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read and validate only, do not write to database",
        )
        parser.add_argument(
            "--export-json",
            default=None,
            help="Export legacy data to JSON file (for inspection/backup)",
        )

    def handle(self, *args, **options):
        db_path = options["db_path"]
        dry_run = options["dry_run"]
        export_json = options["export_json"]

        # ── Determine DB path ──
        if not db_path:
            # Default: <project_root>/log/paycheck.db
            repo_root = os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )
                )
            )
            db_path = os.path.join(repo_root, "log", "paycheck.db")

        self.stdout.write(f"Reading legacy database: {db_path}")

        # ── Step 1: Read legacy DB ──
        try:
            transactions, legacy_summary = read_legacy_db(db_path)
        except FileNotFoundError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            sys.exit(1)

        self.stdout.write(
            f"Found {len(transactions)} records in legacy database"
        )
        self.stdout.write(
            f"  Expense: ¥{legacy_summary['total_expense']:,.2f}"
        )
        self.stdout.write(
            f"  Income:  ¥{legacy_summary['total_income']:,.2f}"
        )

        # ── Step 2: Export JSON (optional) ──
        if export_json:
            with open(export_json, "w", encoding="utf-8") as f:
                json.dump(transactions, f, ensure_ascii=False, indent=2)
            self.stdout.write(
                self.style.SUCCESS(f"Exported {len(transactions)} records to {export_json}")
            )

        # ── Platform mapping stats ──
        bank_count = sum(1 for t in transactions if t.get("_original_platform") == "bank")
        if not bank_count:
            bank_count = sum(1 for t in transactions if t["platform"] == "boc" and t.get("_tag_ids") is not None)
            # Count original bank records
            bank_count = sum(
                1 for t in transactions
                if any(
                    t.get("balance", 0) != 0
                    or t.get("currency", "")
                    or t.get("cp_account", "")
                    for _ in [1]
                )
            )
        self.stdout.write(
            f"Platform mapping: 'bank' → 'boc' applied to all relevant records"
        )

        # ── Step 3: Migrate to Django ──
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no data written"))
            return

        with db_transaction.atomic():
            result = migrate_to_django(transactions)

        self.stdout.write(
            self.style.SUCCESS(
                f"Migration complete: {result['created']} created, "
                f"{result['skipped']} skipped, {result['errors']} errors"
            )
        )

        # ── Step 4: Verify ──
        self.stdout.write("\nVerifying migration...")
        verification = verify_migration(legacy_summary)

        self.stdout.write(f"  Record count: legacy={verification['legacy']['count']}, "
                          f"new={verification['new']['count']} → "
                          f"{'✅' if verification['count_match'] else '❌'}")
        self.stdout.write(f"  Total expense: legacy=¥{verification['legacy']['expense']:,.2f}, "
                          f"new=¥{verification['new']['expense']:,.2f} → "
                          f"{'✅' if verification['expense_match'] else '❌'}")
        self.stdout.write(f"  Total income:  legacy=¥{verification['legacy']['income']:,.2f}, "
                          f"new=¥{verification['new']['income']:,.2f} → "
                          f"{'✅' if verification['income_match'] else '❌'}")

        if all([verification['count_match'], verification['expense_match'], verification['income_match']]):
            self.stdout.write(self.style.SUCCESS("\n✓ Verification passed — all checks match"))
        else:
            self.stderr.write(self.style.ERROR("\n✗ Verification failed — some checks do not match"))
