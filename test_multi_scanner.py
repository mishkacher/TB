from scanners.multi_scanner import MultiScanner


scanner = MultiScanner()


results = scanner.scan()


print("\n🔥 TOP MARKET SIGNALS")
print("--------------------")


for r in results:

    print(
        r["symbol"],
        "|",
        r["signal"],
        "| Scanner:",
        r["score"],
        "| Ranking:",
        r["ranking_score"],
        "| Quality:",
        r["quality"],
    )

    if r["rules"]:
        print("  Reasons:", ", ".join(r["rules"]))
