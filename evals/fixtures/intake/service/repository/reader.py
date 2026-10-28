from flask import Flask, request

app = Flask(__name__)

@app.get("/read")
def read_file():
    return open(request.args["path"]).read()
