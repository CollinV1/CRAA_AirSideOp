from fastapi import FastAPI

app = FastAPI()

''' Define root '''
# app decorator 
@app.get("/") # root directory path, returns root function

# defines root directory function
def root():
    return {"Hello": "World"}

# routes define urls that app responds to 

items = []

# create access to endpoint 
@app.post("/items") # users send HTTP post request to "/items" path

# create endpoint
def create_item(item: str):
    items.append(item)
    return items
