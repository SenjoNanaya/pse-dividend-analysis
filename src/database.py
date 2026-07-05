import pandas as pd
import matplotlib.pyplot as plt

def compute_growth(metric_key, years, company_data):
    values = []
    for y in years:
        if y in company_data["years"] and metric_key in company_data["years"][y]:
            values.append((y, company_data["years"][y][metric_key]))
    if len(values) < 2:
        return {"yoy": {}, "cagr": None}
    
    yoy = {}
    for i in range(len(values)-1):
        prev = values[i][1]
        curr = values[i+1][1]
        if prev and curr and prev != 0:
            yoy[values[i+1][0]] = (curr - prev) / prev
    
    cagr = None
    if len(values) >= 3 and values[0][1] and values[0][1] != 0 and values[-1][1] is not None:
        cagr = (values[-1][1] / values[0][1]) ** (1/(len(values)-1)) - 1
    return {"yoy": yoy, "cagr": cagr}

def generate_report(company_data):
    stock = company_data["stock_data"]
    required_keys = ["eps", "book_value_per_share", "net_income", "total_assets", "gross_revenue"]
    years = [y for y in company_data["years"].keys() if all(k in company_data["years"][y] for k in required_keys)]
    
    if not years:
        print("No complete financial years available.")
        return
    years.sort()
    latest = years[-1]
    dividends = company_data["dividends"]

    growth_bv = compute_growth("book_value_per_share", years, company_data)
    growth_ni = compute_growth("net_income", years, company_data)
    growth_assets = compute_growth("total_assets", years, company_data)
    growth_rev = compute_growth("gross_revenue", years, company_data)
    growth_eps = compute_growth("eps", years, company_data)

    latest_data = company_data["years"][latest]
    pe = stock["last_traded_price"] / latest_data["eps"] if latest_data.get("eps") else None
    pb = stock["last_traded_price"] / latest_data["book_value_per_share"] if latest_data.get("book_value_per_share") else None
    roe = latest_data["net_income"] / latest_data["stockholders_equity"] if latest_data.get("stockholders_equity") else None
    
    total_div_per_share = sum([d["rate"] for d in dividends if d["ex_date"].startswith(str(latest)[:4])])
    div_yield = total_div_per_share / stock["last_traded_price"] if stock["last_traded_price"] else None
    total_div_paid = total_div_per_share * stock["outstanding_shares"] if stock["outstanding_shares"] else 0
    div_cover = latest_data["net_income"] / total_div_paid if total_div_paid else None

    check = {
        "pe_under_22": pe is not None and pe < 22,
        "pb_under_1": pb is not None and pb < 1,
        "bv_increasing": len(years) >= 2 and company_data["years"][years[-1]].get("book_value_per_share", 0) > company_data["years"][years[-2]].get("book_value_per_share", 0),
        "income_increasing": len(years) >= 2 and company_data["years"][years[-1]].get("net_income", 0) > company_data["years"][years[-2]].get("net_income", 0),
        "assets_increasing": len(years) >= 2 and company_data["years"][years[-1]].get("total_assets", 0) > company_data["years"][years[-2]].get("total_assets", 0),
        "shares_diluting": len(years) >= 2 and company_data["years"][years[-1]].get("outstanding_shares", 0) > company_data["years"][years[-2]].get("outstanding_shares", 0),
        "roe_above_10": roe is not None and roe > 0.10
    }

    zero_growth_fv = latest_data.get("eps") / 0.10 if latest_data.get("eps") else None

    # --- Print Report ---
    print("="*80)
    print(f"{stock['company_name']} ({stock['ticker']})")
    print(f"Last Price: {stock['last_traded_price']:.2f} PHP")
    print(f"Market Cap: {stock['market_cap']:,.0f} PHP")
    print("="*80)
    
    # Growth Overview table
    print("\nGROWTH OVERVIEW")
    print("-"*80)
    growth_dict = {
        "Metric": ["Book Value", "Net Income", "Total Assets", "Revenue", "EPS"],
        "YoY 2023→2024": [
            growth_bv["yoy"].get(2024, None),
            growth_ni["yoy"].get(2024, None),
            growth_assets["yoy"].get(2024, None),
            growth_rev["yoy"].get(2024, None),
            growth_eps["yoy"].get(2024, None)
        ],
        "YoY 2024→2025": [
            growth_bv["yoy"].get(2025, None),
            growth_ni["yoy"].get(2025, None),
            growth_assets["yoy"].get(2025, None),
            growth_rev["yoy"].get(2025, None),
            growth_eps["yoy"].get(2025, None)
        ],
        "3‑Year CAGR": [
            growth_bv.get("cagr", None),
            growth_ni.get("cagr", None),
            growth_assets.get("cagr", None),
            growth_rev.get("cagr", None),
            growth_eps.get("cagr", None)
        ]
    }
    df_growth = pd.DataFrame(growth_dict)
    def pct(x):
        return f"{x*100:.1f}%" if x is not None else "N/A"
    df_growth = df_growth.map(lambda x: pct(x) if isinstance(x, float) else x)
    print(df_growth.to_string(index=False))
    
    # Ratios
    print("\nRATIOS")
    print("-"*80)
    ratios = {
        "P/E Ratio": f"{pe:.2f}" if pe is not None else "N/A",
        "P/B Ratio": f"{pb:.2f}" if pb is not None else "N/A",
        "ROE": f"{roe*100:.1f}%" if roe is not None else "N/A",
        "Dividend Yield": f"{div_yield*100:.2f}%" if div_yield is not None else "N/A",
        "Dividend Cover": f"{div_cover:.2f}" if div_cover is not None else "N/A"
    }
    df_ratios = pd.DataFrame(list(ratios.items()), columns=["Metric", "Value"])
    print(df_ratios.to_string(index=False))
    
    # Checklist
    print("\nFUNDAMENTAL CHECKLIST")
    print("-"*80)
    check_labels = {
        "pe_under_22": "P/E Ratio < 22",
        "pb_under_1": "P/B Ratio < 1",
        "bv_increasing": "Book Value Increasing?",
        "income_increasing": "Net Income Increasing?",
        "assets_increasing": "Total Assets Increasing?",
        "shares_diluting": "Shares Diluting? (No = ✓)",
        "roe_above_10": "ROE > 10%"
    }
    for key, label in check_labels.items():
        val = check.get(key)
        if val is None:
            symbol = "?"
        elif val:
            symbol = "✅"
        else:
            symbol = "❌"
        print(f"{label}: {symbol}")
    
    # Valuation
    print("\nVALUATION SCENARIOS (DCF, Required Return = 10%)")
    print("-"*80)
    if zero_growth_fv is not None:
        print(f"Zero Growth Fair Value: {zero_growth_fv:.2f} PHP")
        print(f"Current Price: {stock['last_traded_price']:.2f} PHP")
        margin = (zero_growth_fv - stock['last_traded_price']) / stock['last_traded_price'] * 100
        print(f"Margin of Safety: {margin:.1f}%")
    else:
        print("EPS not available, cannot compute fair value.")
    
    # Bar chart
    metrics_for_chart = ["Book Value", "Net Income", "Total Assets", "Revenue"]
    yoy_2024 = [growth_bv["yoy"].get(2024, 0), growth_ni["yoy"].get(2024, 0), growth_assets["yoy"].get(2024, 0), growth_rev["yoy"].get(2024, 0)]
    yoy_2025 = [growth_bv["yoy"].get(2025, 0), growth_ni["yoy"].get(2025, 0), growth_assets["yoy"].get(2025, 0), growth_rev["yoy"].get(2025, 0)]
    
    # Replace None with 0 for plotting
    yoy_2024 = [v if v is not None else 0 for v in yoy_2024]
    yoy_2025 = [v if v is not None else 0 for v in yoy_2025]
    
    x = range(len(metrics_for_chart))
    width = 0.35
    plt.figure(figsize=(10, 6))
    plt.bar([i - width/2 for i in x], yoy_2024, width, label='2023→2024')
    plt.bar([i + width/2 for i in x], yoy_2025, width, label='2024→2025')
    plt.xticks(x, metrics_for_chart, rotation=45, ha='right')
    plt.ylabel('Growth Rate')
    plt.title(f'{stock["ticker"]} - YoY Growth Rates')
    plt.legend()
    plt.tight_layout()
    plt.show()