import pathlib

base = pathlib.Path(r"C:\Users\Vicky\Desktop\bitemporal-ledger\dashboard\PortfolioReport\PortfolioReport.SemanticModel\definition\tables")

def write_table(filename, table, tag, measures, columns, item):
    lines = [f"table {table}", f"\tlineageTag: {tag}", ""]
    for name, dax in measures:
        lines.append(f"\tmeasure {name} = {dax}")
        lines.append("")
    for col, dtype, summ in columns:
        lines.append(f"\tcolumn {col}")
        lines.append(f"\t\tdataType: {dtype}")
        lines.append(f"\t\tsummarizeBy: {summ}")
        lines.append(f"\t\tsourceColumn: {col}")
        lines.append("")
    lines.append(f"\tpartition {table} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t\tlet")
    lines.append('\t\t\t\t\tSource = PostgreSQL.Database("localhost:5434", "bitemporal_ledger"),')
    lines.append("\t\t\t\t\t{0} = Source{{[Schema=\"marts\", Item=\"{1}\"]}}[Data]".format(item, item))
    lines.append("\t\t\t\tin")
    lines.append("\t\t\t\t\t{0}".format(item))
    lines.append("")
    text = "\n".join(lines).replace("\n", "\r\n")
    (base / f"{filename}").write_text(text)
    print("rewrote", table)

write_table(
    "HoldingsSnapshot.tmdl", "HoldingsSnapshot", "10000000-1000-4000-8000-000000000007",
    [("HoldingsValue", "SUM(HoldingsSnapshot[value])")],
    [
        ("account_id", "int64", "none"),
        ("scheme_code", "string", "none"),
        ("units", "decimal", "sum"),
        ("value", "decimal", "sum"),
        ("is_stale", "string", "none"),
        ("nav_date", "dateTime", "none"),
    ],
    "holdings_snapshot",
)

write_table(
    "RejectedCorrections.tmdl", "RejectedCorrections", "10000000-1000-4000-8000-000000000008",
    [("RejectedCount", "COUNTROWS(RejectedCorrections)")],
    [
        ("txn_group_id", "string", "none"),
        ("correction_type", "string", "none"),
        ("reason_code", "string", "none"),
        ("actor_id", "string", "none"),
        ("attempted_recorded_at", "dateTime", "none"),
    ],
    "rejected_corrections",
)

model = pathlib.Path(r"C:\Users\Vicky\Desktop\bitemporal-ledger\dashboard\PortfolioReport\PortfolioReport.SemanticModel\definition\model.tmdl")
text = model.read_text()
for extra in ("ref table HoldingsSnapshot", "ref table RejectedCorrections"):
    if extra not in text:
        text = text.replace("ref table Sensitivity", extra + "\r\n\r\nref table Sensitivity")
model.write_text(text)
print("model updated")
