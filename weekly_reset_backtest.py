import pandas as pd
from datetime import timedelta
from weather_bot import generate_demo_history, simulate_strategy, BacktestConfig

def run_weekly_reset_backtest():
    print("Generating 180 days (approx 25 weeks) of realistic demo data...")
    # Generate realistic data without "knowing the future"
    rows = generate_demo_history(days=180, seed=42)
    
    # Convert 'date' to datetime objects to extract the week
    rows['date'] = pd.to_datetime(rows['date'])
    
    # Define our aggressive but house-money protected config
    config = BacktestConfig(
        initial_bankroll=3.0,
        edge_threshold=0.03,
        kelly_fraction=1.0,
        min_entry_price=0.10,
        max_entry_price=0.60,
        min_trade_size=0.50,
        max_trade_size=150.0,
        max_trade_fraction=1.0,
        allow_min_size_round_up=True
    )
    
    # Sort by date
    rows = rows.sort_values('date')
    
    # Group by year and ISO week
    rows['year_week'] = rows['date'].dt.strftime('%Y-%V')
    weeks = rows['year_week'].unique()
    
    print("\n--- Weekly Reset Backtest Results ---")
    print(f"{'Week':<10} | {'Trades':<8} | {'Starting':<10} | {'Ending':<10} | {'Weekly PnL':<10}")
    print("-" * 60)
    
    total_pnl = 0.0
    wins = 0
    losses = 0
    bankruptcies = 0
    
    for week in weeks:
        week_rows = rows[rows['year_week'] == week]
        
        # Simulate strategy for just this week. 
        # Bankroll resets to $3 at the start of every week in simulate_strategy!
        trades = simulate_strategy(week_rows, config)
        
        trade_count = len(trades)
        starting = 3.0
        
        if trade_count > 0:
            ending = trades.iloc[-1]['bankroll_after']
        else:
            ending = starting
            
        pnl = ending - starting
        total_pnl += pnl
        
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
            
        if ending < 0.50: # Effectively bankrupt, can't make trades
            bankruptcies += 1
            
        print(f"{week:<10} | {trade_count:<8} | ${starting:<9.2f} | ${ending:<9.2f} | ${pnl:<9.2f}")
        
    print("-" * 60)
    print(f"Total Weeks Tested: {len(weeks)}")
    print(f"Winning Weeks: {wins}")
    print(f"Losing Weeks: {losses}")
    print(f"Weeks Gone Bankrupt (Under $0.50): {bankruptcies}")
    print(f"Average Weekly PnL: ${total_pnl / len(weeks):.2f}")
    print(f"Total Sum of Weekly PnLs: ${total_pnl:.2f}")

if __name__ == '__main__':
    run_weekly_reset_backtest()