import pickle
from datetime import datetime

date = datetime.today().strftime('%Y-%m-%d')
try:
    with open('dates_on_record.pkl', 'rb') as f:
        record = pickle.load(f)
except:
    record = []

if date not in record:
    record.append(date)
    with open('dates_on_record.pkl','wb') as f:
        pickle.dump(record,f)
