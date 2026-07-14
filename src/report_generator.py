import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from src.utils import safe_float, format_safe
from src.parser import sanitize_per_share_price
import os

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
    if len(values) >= 2:
        first = values[0][1]
        last = values[-1][1]
        # CAGR is only meaningful for sustained positive values
        if first and last is not None and first > 0 and last > 0:
            ratio = last / first
            if ratio > 0:
                cagr = ratio ** (1 / (len(values) - 1)) - 1
    return {"yoy": yoy, "cagr": cagr}

def generate_report(company_data):
    os.makedirs("reports", exist_ok=True)

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
    
    eps = safe_float(latest_data.get("eps"))
    book_value = safe_float(latest_data.get("book_value_per_share"))
    net_income = safe_float(latest_data.get("net_income"))
    equity = safe_float(latest_data.get("stockholders_equity"))

    stock["last_traded_price"] = safe_float(stock.get("last_traded_price"))
    stock["outstanding_shares"] = safe_float(stock.get("outstanding_shares"))
    stock["market_cap"] = safe_float(stock.get("market_cap"))

    sanitized_price, _ = sanitize_per_share_price(
        stock["last_traded_price"],
        stock["market_cap"],
        stock["outstanding_shares"],
    )
    stock["last_traded_price"] = sanitized_price

    pe = safe_float(stock.get("pe_ratio"))
    pb = safe_float(stock.get("pb_ratio"))
    if pe is not None and abs(pe) > 1000:
        pe = None
    if pb is not None and abs(pb) > 1000:
        pb = None
    if pe is None and eps and stock["last_traded_price"]:
        pe = stock["last_traded_price"] / eps
    if pb is None and book_value and stock["last_traded_price"]:
        pb = stock["last_traded_price"] / book_value
    roe = safe_float(stock.get("roe"))
    if roe is None and equity and net_income:
        roe = net_income / equity
    
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
        "shares_diluting": (
            len(years) >= 2
            and (company_data["years"][years[-1]].get("outstanding_shares") is not None)
            and (company_data["years"][years[-2]].get("outstanding_shares") is not None)
            and company_data["years"][years[-1]]["outstanding_shares"]
            > company_data["years"][years[-2]]["outstanding_shares"] * 1.001
        ) if (
            len(years) >= 2
            and company_data["years"][years[-1]].get("outstanding_shares") is not None
            and company_data["years"][years[-2]].get("outstanding_shares") is not None
        ) else None,
        "roe_above_10": roe is not None and roe > 0.10
    }

    zero_growth_fv = eps / 0.10 if eps else None

    # --- Print Report ---
    print("="*80)
    print(f"{stock['company_name']} ({stock['ticker']})")
    print(f"Last Price: {format_safe(stock['last_traded_price'], '.2f')} PHP")
    print(f"Market Cap: {format_safe(stock['market_cap'], ',.0f')} PHP")
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
        if x is None or isinstance(x, complex) or (isinstance(x, float) and np.isnan(x)):
            return "N/A"
        return f"{x*100:.1f}%" if isinstance(x, (int, float)) else x
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
        if key == "shares_diluting":
            # Pass when NOT diluting (align with UI "NO Share Dilution")
            if val is None:
                symbol = "?"
            else:
                symbol = "✅" if not val else "❌"
        elif val is None:
            symbol = "?"
        elif val:
            symbol = "✅"
        else:
            symbol = "❌"
        print(f"{label}: {symbol}")
    
    # Valuation
    print("\nVALUATION SCENARIOS (DCF, Required Return = 10%)")
    print("-"*80)
    if zero_growth_fv is not None and stock['last_traded_price'] is not None and stock['last_traded_price'] != 0:
        print(f"Zero Growth Fair Value: {format_safe(zero_growth_fv, '.2f')} PHP")
        print(f"Current Price: {format_safe(stock['last_traded_price'], '.2f')} PHP")
        margin = ((zero_growth_fv - stock['last_traded_price']) / stock['last_traded_price']) * 100
        print(f"Margin of Safety: {format_safe(margin, '.1f')}%")
    else:
        print("Insufficient data to calculate Margin of Safety.")
    
    metrics_to_plot = [
        ('gross_revenue', 'Revenue'),
        ('net_income', 'Net Income'),
        ('total_assets', 'Total Assets')
    ]

    # Get available years
    years = sorted([y for y in company_data["years"].keys() if y is not None])
    
    if len(years) < 2:
        print(f"Not enough years ({len(years)}) to generate dashboard for {stock['ticker']}.")
    else:
        # Create a figure with 3 subplots (3 rows, 1 column)
        fig, axes = plt.subplots(3, 1, figsize=(12, 15))
        fig.suptitle(f'{stock["ticker"]} - Financial Performance Dashboard', 
                     fontsize=16, fontweight='bold', y=0.98)
        
        dashboard_has_data = False
        
        for idx, (metric_key, label) in enumerate(metrics_to_plot):
            ax = axes[idx]  # Get the axis for this subplot
            
            # Extract data safely
            values = []
            valid_years = []
            for year in years:
                val = safe_float(company_data["years"].get(year, {}).get(metric_key))
                if val is not None:
                    values.append(val)
                    valid_years.append(year)
            
            # Check if we have valid data to plot (at least 2 points, and not all zeros)
            if len(valid_years) >= 2 and not all(v == 0 for v in values):
                dashboard_has_data = True
                values_millions = [v / 1_000_000 for v in values]
                
                # --- Plot 1: Bars ---
                bars = ax.bar(valid_years, values_millions, 
                              color='#2E86AB', edgecolor='black', linewidth=1.0, 
                              alpha=0.75, label='Annual Value')
                
                # --- Plot 2: Trend Line ---
                ax.plot(valid_years, values_millions, 
                        marker='o', linestyle='-', linewidth=2.5, markersize=8,
                        color='#D32F2F', label='Trend')
                
                # --- Add value labels on bars (handles negatives) ---
                min_val, max_val = min(values_millions), max(values_millions)
                range_val = max_val - min_val if max_val != min_val else 1
                label_padding = abs(range_val) * 0.05  # 5% padding
                
                for bar, val in zip(bars, values_millions):
                    if val >= 0:
                        y_pos = bar.get_height() + label_padding
                        va = 'bottom'
                    else:
                        y_pos = bar.get_height() - label_padding
                        va = 'top'
                    
                    ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                            f'{val:,.1f}M', ha='center', va=va, 
                            fontsize=9, fontweight='bold')
                
                # --- Set Y-axis limits with padding ---
                if min_val == max_val:
                    padding = abs(max_val) * 0.2 if max_val != 0 else 5
                    ax.set_ylim(min_val - padding, max_val + padding)
                else:
                    padding = abs(range_val) * 0.15
                    ax.set_ylim(min_val - padding, max_val + padding)
                
                # --- Zero baseline (critical for negative values) ---
                ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8, alpha=0.4)
                
                # --- Formatting ---
                ax.set_title(label, fontsize=12, fontweight='bold', loc='left')
                ax.set_ylabel('Millions PHP', fontsize=10)
                ax.grid(axis='y', linestyle='--', alpha=0.3)
                ax.set_xticks(valid_years)
                ax.legend(loc='upper left', fontsize=9)
            
            else:
                # No data or all zeros — show a placeholder message
                ax.text(0.5, 0.5, f'No Data Available for {label}', 
                        horizontalalignment='center', verticalalignment='center', 
                        transform=ax.transAxes, fontsize=12, color='gray')
                ax.set_title(label, fontsize=12, fontweight='bold', loc='left')
                ax.set_xticks([])
                ax.set_yticks([])
                # Remove border for empty charts
                for spine in ax.spines.values():
                    spine.set_visible(False)

        # Only save if at least one chart had data
        if dashboard_has_data:
            plt.tight_layout(rect=[0, 0, 1, 0.96])  # Make room for the main title
            
            os.makedirs("reports", exist_ok=True)
            filename = f"reports/{stock['ticker']}_dashboard.png"
            plt.savefig(filename, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"  Dashboard saved: {filename}")
        else:
            plt.close()
            print(f"  No data available to generate dashboard for {stock['ticker']}.")