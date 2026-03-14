import pandas as pd
from sqlalchemy import create_engine

'''
purpose: loads .csv into supabase db
    - reads .csv into pandas dataframe 
    - uploads to db

requirements: 
    pip install SQLAlchemy
'''

def pandas_to_sql(csv_filepath, table_name, db_uri):
    # read .csv --> dataframe
    df = pd.read_csv(csv_filepath)

    # create db engine
    engine = create_engine(db_uri)

    # upload to supabase
    df.to_sql(table_name, con=engine, index=False, if_exists='append')
    print(f"Data from {csv_filepath} sucessfully appended to table {table_name}.")
    
