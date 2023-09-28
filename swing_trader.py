from datetime import datetime, timezone
from datetime import date as date_obj
import datetime as DT

import calendar
import time
import pickle


from bs4 import BeautifulSoup
import requests
import numpy as np
import pandas as pd

import yfinance as yf
import requests

import alpaca_trade_api as api
import math


#---------------- Credentials -----------------------------------------------

API_KEY = ""
API_SECRET = ""
BASE_URL = "https://api.alpaca.markets"

gainer_data_url = "https://finance.yahoo.com/gainers"

alpaca = api.REST(API_KEY, API_SECRET, BASE_URL)
account = alpaca.get_account()


#---------------- Stategy ---------------------------------------------------------------------------------------------
SWING_TRADER_START_TIME = 10 # Number of minutes to wait after market open before starting the SWING trading strategy.

PERCENT_GAIN = 1.01 # Mark for sale after a stock that owned appreciates by this percentage
PERCENT_DROP = 0.95 # Mark for purchase after a stock that is being tracked depreciates by this percentage


BUY_RISE = 1.025 # Execute Buy when a stock that is marked for purchase appreciates by this percentage in value
SELL_DROP = 0.975 # Execute Sell when a stock that is marked for sale depreciates by this percentage in value

PERCENT_STOP_LOSS = 0.95 # Stop loss if a stock that is held depreciates by this percentage from the buying cost
#-------------------------------- HELPER FUNCTIONS --------------------------------------------------------------------


def check_tumble(data):
    """"
    Based on historical data over some timeframe, return True if the average price at the the end is lower than the average price 
    at the start - i.e the stock has tumbled.
    """
    A = sum([data[i] for i in range(3)])/3
    B = sum([data[-i] for i in range(3)])/3
    if B-A<0:   # A drop 
        return True
    return False

def check_for_FPT(symbol):
    """
    For a symbol in the top gainers list, check that the stock has a history as a tumbling stock over the past day, month and 
    year (i.e flash-point). If it is a flash point, record the flask point (highest point), and set limit buy and sell prices 
    along with the stop-loss.
    """
    FPT = False
    flash_point = None
    limit_buy_price = None
    limit_sell_price = None
    stop_loss = None
    
    # Flash point trading logic --------------------------------------------------------------------------------
    
    #Pull Historical data
    
    try:
        one_day_data = yf.download(tickers=symbol, period='1d', interval='2m')['Open']
        one_month_data = yf.download(tickers=symbol, period='1mo', interval='1d')['Open']
        three_month_data = yf.download(tickers=symbol, period='3mo', interval='1d')['Open']

    except:
        return (FPT, flash_point, limit_buy_price, limit_sell_price, stop_loss)
    
    # check for a tumble on a one week, one month and three month scale
    if len(one_day_data)>0 and len(three_month_data)>5 and len(one_month_data)>5 and check_tumble(three_month_data) and check_tumble(one_month_data):
        
        FPT = True
        #Record highest point on a one day scale
        flash_point = max(one_day_data)
        
        current_price = float(alpaca.get_latest_trade(symbol).p)
        
        limit_buy_price = flash_point * PERCENT_DROP
        limit_sell_price = PERCENT_GAIN * limit_buy_price
        stop_loss = PERCENT_STOP_LOSS * limit_buy_price
    else:
        FPT = False
        
    return (FPT, flash_point, limit_buy_price, limit_sell_price, stop_loss)


def revise_flash_point(symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss):
    """
    Revise the flash point if the tracked stock rises again before it is bought. 
    """
    try:
        one_day_data = yf.download(tickers=symbol, period='1d', interval='2m')['Open']
        revised_flash_point = max(one_day_data)
        current_price = float(alpaca.get_latest_trade(symbol).p)
        if revised_flash_point>flash_point:
            flash_point = revised_flash_point
        if current_price>flash_point:
            flash_point = current_price

        limit_buy_price = flash_point * PERCENT_DROP

        limit_sell_price = PERCENT_GAIN * limit_buy_price
        stop_loss = PERCENT_STOP_LOSS * limit_buy_price
    except:
        print('Could not revise flash point... using old data.')
    return (flash_point, limit_buy_price, limit_sell_price, stop_loss)



def count_days_interval(date1, date2):
    """
    Returns absolute difference between two dates so that ordering of dates is not important. (Bussiness Days)
    """
    year1, month1, day1 = date1.split('-')
    year1 = int(year1)
    month1 = int(month1)
    day1 = int(day1)
    
    year2, month2, day2 = date2.split('-')
    year2 = int(year2)
    month2 = int(month2)
    day2 = int(day2)
    
    f_date = date_obj(year2, month2, day2)
    l_date = date_obj(year1, month1, day1)

    return np.abs(np.busday_count(f_date, l_date))
    
def check_greater_than_eq(date1, date2):
    """
    Returns true if date2 is after date1 (Bussiness Days)
    """
    year1, month1, day1 = date1.split('-')
    year1 = int(year1)
    month1 = int(month1)
    day1 = int(day1)

    year2, month2, day2 = date2.split('-')
    year2 = int(year2)
    month2 = int(month2)
    day2 = int(day2)

    f_date = date_obj(year2, month2, day2)
    l_date = date_obj(year1, month1, day1)

    if int(np.busday_count(f_date, l_date))>=0:
        return True
    return False
    
def check_returnFlash(data, record_date, record_time, flash_point):
    """
    Returns true if the a later-date price is greater than the recorded flash point.
    """
    h, m = record_time
    for tme, price in zip(data.index, data):
        data_date, time = str(tme).split(' ')
        time = time.split('-')[0]
        t_h, t_m, _ = time.split(':')
        t_h = int(t_h)
        t_m = int(t_m)
        
        if price>flash_point and check_greater_than_eq(data_date, record_date) and (t_h>h or t_m>=m+15):
            return True # Return to flash point
        
    return False       

        
def flash_point_revisited(record_date, record_time, symbol, flash_point):
    """
    Returns True if the flash point has been revisited since the record_date and time.
    """
    flash_point = flash_point *0.97 # Allow inexact lowerbound
    
    #Pull Historical data
    try:
        one_day_data = yf.download(tickers=symbol, period='1d', interval='2m')['Open']
        one_week_data = yf.download(tickers=symbol, period='1w', interval='5m')['Open']
        one_month_data = yf.download(tickers=symbol, period='1mo', interval='1d')['Open']
    
        c1 = check_returnFlash(one_day_data, record_date, record_time, flash_point)
        c2 = check_returnFlash(one_week_data, record_date, record_time, flash_point)
        c3 = check_returnFlash(one_month_data, record_date, record_time, flash_point)
    except:
        return False
    if c1 or c2 or c3:
        return True # Return to flash point
    
    return False

def execute_buy(symbol,price):
    """
    Get buying power, compute maximum affordable shares for the given symbol and place the alpaca API buy order for that qty.
    """
    buying_power = float(account.buying_power)
    current_price = float(alpaca.get_latest_trade(symbol).p)
    price = math.floor(price*100)/100.0
    qty = math.floor(buying_power*100/price)/100.0
    print('Buying Power', buying_power)
    print('Current Price*qty',qty*current_price)


    if qty<=0:
        return 0
    else:
        try:
            print(symbol, qty, price)
            order = alpaca.submit_order(symbol, qty=qty, side='buy')
            
            # Sleep 120sec to allow the order to execute, also avoid too many API calls per minute (atmost 200 per minute allowed).
            time.sleep(120)

            alpaca.cancel_all_orders() # Cancel the order if it has not been executed.
            
            if symbol in str(alpaca.list_positions()[0]):
                if symbol in quantity_owned:
                    quantity_owned[symbol]+=qty
                else:
                    quantity_owned[symbol] = qty
                return 2 # Success
            else:
                alpaca.cancel_all_orders() # Cancel pending limit order.
                return 1 # Failure
        except:
            alpaca.cancel_all_orders() # Cancel pending limit order.
            return 1
    
def execute_sell(symbol, price):
    """
    Retrieve the qty shares owned for the given symbol and place the alpaca API sell order for that qty.
    """
    qty = quantity_owned[symbol]
    price  = math.floor(price*100)/100.0
    try:
        order = alpaca.submit_order(symbol, qty=qty, side='sell') # type='limit', limit_price=price)
        
        # Sleep 120sec to allow the order to execute, also avoid too many API calls per minute (atmost 200 per minute allowed).
        time.sleep(120)
        
        alpaca.cancel_all_orders() # Cancel the order if it has not been executed.

        if symbol not in str(alpaca.list_positions()[0]):
            del quantity_owned[symbol]
            return 2 # Success
        else:
            alpaca.cancel_all_orders() # Cancel pending limit order.
            return 1 # Failure
            
    except:
        alpaca.cancel_all_orders() # Cancel pending limit order.
        return 1

def get_background_info():
    """
    Get the date, check if the market is open and if it is a good time to start swing trading according to the strategy.
    """
    curr_date = datetime.today()
    day_of_week = calendar.day_name[curr_date.weekday()]
        
    date = datetime.today().strftime('%Y-%m-%d')
        
    year, month, day = date.split('-')
    year = int(year)
    month = int(month)
    day = int(day)

    if day_of_week in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        weekday = True
    else:
        weekday = False
    

    dt = datetime.now()
    dt = dt.replace(tzinfo=timezone.utc)

    current_time = dt.strftime("%H:%M:%S")
    h,m,s = current_time.split(':')

    # Account for day light savings
    if month>=3 and month<=11:
        if month==3 and day<14:
            time_difference =5
        elif month==11 and day>=7:
            time_difference =5
        else:
            time_difference = 4
    else:
        time_difference = 5
    
    # Get NYSE time
    h = int(h) - time_difference
    m = int(m)
    s = int(s)

    # Market Open/Close in new-york time (Close half hour early to avoid odd behaviour)
    market_open_time = (9,30,0)
    market_close_time = (16,30,0)

    if weekday and market_open_time[0]<=h and market_close_time[0]>h:
        if market_open_time[0]<h or (market_open_time[0]==h and market_open_time[1]<=m):
            market_open = True
        else:
            market_open = False
    else:
        market_open = False
    
    # Set flash-point-time   (NEEDS to be corrected for 15 min delay in yahoo stock price.)-- trade after fp+15
    flash_point_start = SWING_TRADER_START_TIME + 15 #min same hour as market open
    if market_open and (h > market_open_time[0]  or (m - market_open_time[1])>=flash_point_start):
        flash_time = True
    else:
        flash_time = False
    
    return (date, (h,m), market_open, flash_time)

def cool_track_sub_routine(cool_track, track, symbol, limit_buy_price, current_price):
    """
    After a stock is marked for purchase, wait for a BUY_RISE rise before buying in.
    """
    (record_date, record_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss) = track
    if symbol not in cool_track:
        cool_track[symbol] = (current_price, limit_buy_price, current_price)
    elif cool_track[symbol][0]>current_price:
        cool_track[symbol]  = (current_price, limit_buy_price, current_price)
    else:
        cool_track[symbol] = (cool_track[symbol][0], limit_buy_price, current_price)
        
    (lowest_price, limit_buy_price, current_price) = cool_track[symbol]
    
    if current_price>=BUY_RISE*lowest_price:
        print('Trying to buy ', symbol)
        try:
            success_code = execute_buy(symbol, limit_buy_price)
            return cool_track, success_code
        except: 
            print('Unknown API side error...')
        

    return cool_track, 1


def hot_track_sub_routine(hot_track, track, symbol, limit_sell_price, current_price) :
    """
    After a stock is marked for sale, wait for a SELL_DROP before selling.
    """
    (record_date, record_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss) = track
    if symbol not in hot_track:
        hot_track[symbol] = (current_price, limit_sell_price, current_price)
    elif hot_track[symbol][0]<current_price:
        hot_track[symbol]  = (current_price, limit_sell_price, current_price)
    else:
        hot_track[symbol] = (hot_track[symbol][0], limit_sell_price, current_price)
        
    (highest_price, limit_sell_price, current_price) = hot_track[symbol]
    
    if current_price<=SELL_DROP*highest_price:
        print('Trying to sell ', symbol)
        try:
            success_code = execute_sell(symbol, limit_sell_price)
            return hot_track, success_code
        except: 
            print('Unknown API side error...')

    return hot_track, 1

#----------------------------------- START OF TRADER LOGIC ----------------------------------------------------------------
holdings = []
current_track = []
cool_track = {}
hot_track = {}
dates_on_record = []
quantity_owned = {}

while True:
    
    # Sleep 10sec to avoid too many API calls per minute (atmost 200 per minute allowed).
    time.sleep(10)
    (date, current_time, market_open, flash_time) = get_background_info()

    if not market_open:
        continue # Wait for the market to open.

    # Read info from files if records exist.--------------------------------------------------------------------------------
    try:
        if holdings==[]:
            with open('./holdings.pkl','rb') as f:
                holdings = pickle.load(f)
    except:
        print('Couldnt read holding file...maybe no prior records exist...') # No records.
    try:
        if current_track==[]:
            with open('./current_track.pkl','rb') as f:
                current_track = pickle.load(f)
    except:
        print('Couldnt read current_track file...maybe no prior records exist...') # No records.
    try:
        if cool_track=={}:
            with open('./cool_track.pkl','rb') as f:
                cool_track = pickle.load(f)
    except:
        print('Couldnt read cool_track file...maybe no prior records exist...') # No records.
    try:
        if hot_track=={}:
            with open('./hot_track.pkl','rb') as f:
                hot_track = pickle.load(f)
    except:
        print('Couldnt read hot_track file...maybe no prior records exist...') # No records.
    try:
        if dates_on_record==[]:
            with open('./dates_on_record.pkl','rb') as f:
                dates_on_record = pickle.load(f)
    except:
        print('Couldnt read dates_on_record file...maybe no prior records exist...') # No records.
    try:
        if quantity_owned=={}:
            with open('./quantity.pkl','rb') as f:
                quantity_owned = pickle.load(f)
    except:
        print('Couldnt read quantity file...maybe no prior records exist...') # No records.

    # Drop day trades record older than 6 bussiness days. (The extra 1 day buffer is to account for odd stock market holidays).
    while market_open and len(dates_on_record)>0 and count_days_interval(dates_on_record[0], date)>6:
        del dates_on_record[0]

    # Start tracking new stocks if the old ones have expired and holdings are zero.----------------------------------------------
    if len(current_track)<1000 and len(holdings)==0:
    
        (date, current_time, market_open, flash_time) = get_background_info()
        
        if flash_time and market_open: 
            print('Within Flash Time...Looking for good trades...')
            # Sleep 30sec to avoid too many API calls per minute (atmost 200 per minute allowed).
            time.sleep(30)
            soup = BeautifulSoup(requests.get(gainer_data_url).text, 'html.parser')
            assets = soup.find_all('a', attrs={"class":"Fw(600)"})
            top_gainers = [str(a).split('<')[-2].split('>')[-1] for a in assets if 'quoteLink' in str(a)]
            print(top_gainers)
            
            # Check the top_gainers list for suitable SWING stocks (flash-points)
            for symbol in top_gainers:
                try:
                    FPT, flash_point, limit_buy_price, limit_sell_price, stop_loss = check_for_FPT(symbol)
                except:
                    continue

                if FPT:
                    flag_check=False
                    entry_num = None
                    for p, track_check in enumerate(current_track):
                        (date_c, current_time_c, symbol_c, flash_point_c, limit_buy_price_c, limit_sell_price_c, stop_loss_c) = track_check
                        if symbol_c == symbol and flash_point_c>=flash_point:
                            flag_check = True
                        elif symbol_c ==symbol and flash_point_c< flash_point:
                            entry_num = p
                            flag_check = False
                    if entry_num != None:
                        del current_track[entry_num]

                    if not flag_check:
                        print('Found a potential Flash Point Trade...symbol: ', symbol, ' starting watch on price action.')
                        current_track.append((date, current_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss))
                    
    print('OUTSIDE!')
    
    # Try to buy at a good price from current_track list-----------------------------------------------------------------------
    if len(current_track)!=0 and len(holdings)==0:    
        revised_track = []
        bought =False
        for i, track in enumerate(current_track):
            (record_date, record_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss) = track
            flash_point, limit_buy_price, limit_sell_price, stop_loss = revise_flash_point(symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss)
            track = (record_date, record_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss)
            print('Tracking ', symbol)
            try:
                current_price = float(alpaca.get_latest_trade(symbol).p)
                print('Current Price of ', symbol,' : ', current_price,'    Target : ', limit_buy_price)
            except:
                print('Failed to get price for ',symbol,'...')
                continue
            
            if current_price <=0:
                print('Failed to get price for ', symbol,' showing less than zero...')
                print('Still going to track though...')

            if not bought and current_price <= limit_buy_price and current_price>0:
                if len(dates_on_record)>=3:
                    print('Not going to buy because we already have 3 day-trader dates on record...')
                    continue
                print('Entering cool track sub routine for ',symbol,'.')
                cool_track, success_code = cool_track_sub_routine(cool_track, track, symbol, limit_buy_price, current_price)
                if success_code ==2:
                    print('Bought ',symbol,'.')
                    stop_loss = current_price* PERCENT_STOP_LOSS # Reset the stop-loss based on actuals
                    limit_sell_price = current_price* PERCENT_GAIN # Reset the selling price based on actuals
                    holdings.append((date, current_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss))
                    bought = True
                    continue
                elif success_code ==1:
                    print('Failed to buy ',symbol,' could have failed cool track criteria or raised API side error...resuming watch.')
                else:
                    print('Failed to buy ',symbol,' insufficient funds...resuming watch.')
            
            revised_track.append(track)
        
        current_track = revised_track
                   
    # Try to sell at a good price from holdings (also sell if STOP_LOSS is reached)----------------------------------------------
    if len(holdings)!=0:
        
        for i, track in enumerate(holdings):
            (record_date, record_time, symbol, flash_point, limit_buy_price, limit_sell_price, stop_loss) = track
            print('Watching ', symbol,' to sell holdings...')
            try:
                current_price = float(alpaca.get_latest_trade(symbol).p)
                print('Current Price of ',symbol, ' : ', current_price, '    TARGET SELL: ', limit_sell_price)
            except:
                print('Failed to get current price...')
                continue
            if current_price>=limit_sell_price:
                print('Entering hot track sub routine for ',symbol,'.')
                hot_track, success_code = hot_track_sub_routine(hot_track, track, symbol, limit_sell_price, current_price)
                if success_code ==2:
                    if count_days_interval(record_date, date)==0:
                        # Day Trade!
                        dates_on_record.append(date)
                    
                    print('Sold ', symbol, '.')
                    holdings = []
                    current_track = [] # Reset the current track.
                else:
                    print('Failed to sell ', symbol, ' unknown API side error.')

            elif current_price<=stop_loss:
                print('Trying to sell ', symbol, 'at stop loss. (LOSS!)')
                success_code = execute_sell(symbol, current_price)
                if success_code ==2:
                    if count_days_interval(record_date, date)==0:
                        # Day Trade!
                        dates_on_record.append(date)
                            
                    print('Sold ', symbol, '.')
                    holdings = []
                    current_track = [] # Reset the current track.
                else:
                    print('Failed to sell ', symbol, ' unknown API side error.')
                    
            
    # Write info to files-----------------------------------------------------------------------------------------------------
    try:
        with open('./holdings.pkl','wb') as f:
            pickle.dump(holdings, f)
        with open('./current_track.pkl','wb') as f:
            pickle.dump(current_track, f)
        with open('./cool_track.pkl','wb') as f:
            pickle.dump(cool_track, f)
        with open('./hot_track.pkl','wb') as f:
            pickle.dump(hot_track, f)
        with open('./dates_on_record.pkl','wb') as f:
            pickle.dump(dates_on_record, f)
        with open('./quantity.pkl','wb') as f:
            pickle.dump(quantity_owned, f)
    except:
        print('Writing files failed for some reason...')
