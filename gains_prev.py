# Initial parameters
initial_balance = 5000  # Initial capital in dollars
gain_per_trade = 0.0001  # 0.01% gain
trades_per_day = 50  # Number of trades per day
days = 30  # Number of days for the projection

# Calculate the compounded balance after given days
final_balance = initial_balance * ((1 + gain_per_trade) ** (trades_per_day * days))

# Calculate the total earnings
total_earnings = final_balance - initial_balance

print(f"Started with {initial_balance}$, traded during {days} days, the total eranings were {total_earnings}$, with a final balace of {final_balance}$")