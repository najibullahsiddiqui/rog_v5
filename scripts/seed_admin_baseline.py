from __future__ import annotations

from app.repositories import AdminRepository


def run() -> None:
    repo = AdminRepository()

    baseline_categories = [
        ("patent", "Patent"),
        ("trademark", "Trademark"),
        ("copyright", "Copyright"),
        ("design", "Design"),
        ("gi", "GI"),
    ]

    existing = {c.get("code") for c in repo.list_categories(include_inactive=True)}
    created = 0
    for code, name in baseline_categories:
        if code in existing:
            continue
        repo.create_category(code=code, name=name, description=f"Baseline category: {name}")
        created += 1

    if not repo.list_data_sources():
        repo.create_data_source(
            name="Local PDF Folder",
            source_type="pdf_folder",
            source_format="pdf",
            uri="data/source_pdfs",
        )

    print(f"Seed complete. Categories created: {created}")


if __name__ == "__main__":
    run()
