import os
import json
import datetime
from flask import Flask, request, Response
import requests

# Configure Proxy Target
TARGET_URL = "http://192.168.2.149:11434"  # Change to your target

app = Flask(__name__)

def create_log_dir():
    """Creates a new subdirectory for each transaction."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = f"logs/{timestamp}"
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def proxy(path):
    log_dir = create_log_dir()

    # Capture request details
    metadata = {
        "timestamp": datetime.datetime.now().isoformat(),
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "query_params": dict(request.args),
    }

    # Save metadata
    with open(os.path.join(log_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

    # Save request body (if any)
    request_body = request.get_data()
    if request_body:
        with open(os.path.join(log_dir, "request_body.json"), "wb") as f:
            f.write(request_body)

    # parse the request body as JSON if possible and modify a field
    try:
        request_json = json.loads(request_body)
        # Modify the request_json as needed
        # For example, if you want to change a field:
        # request_json["field_name"] = "new_value"

        # if there is a field called "max_tokens", remove it.
        if "max_tokens" in request_json and path == "v1/chat/completions":
            del request_json["max_tokens"]

            # if there is no field called "options", add it
            if "options" not in request_json:
                request_json["options"] = {}

            # if there is a field called "options" and it is not a dict, print a warning
            if not isinstance(request_json["options"], dict):
                print("Warning: options is not a dict")
            else:
                request_json["options"]["num_predict"] = 4096
                request_json["options"]["num_ctx"] = 70000




        request_body = json.dumps(request_json).encode('utf-8')
    except json.JSONDecodeError:
        pass
    except TypeError:
        # Handle the case where request_body is None or not a valid JSON
        pass
    # Save the modified request body
    with open(os.path.join(log_dir, "modified_request_body.json"), "wb") as f:
        f.write(request_body)



    # Proxy the request with streaming enabled
    response = requests.request(
        method=request.method,
        url=f"{TARGET_URL}/{path}",
        headers={key: value for key, value in request.headers.items() if key.lower() != "host"},
        params=dict(request.args),
        data=request_body,
        stream=True
    )

    # Stream and log the response body incrementally
    def generate_stream():
        log_path = os.path.join(log_dir, "response_body.json")
        with open(log_path, "wb") as log_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    log_file.write(chunk)
                    yield chunk

    # Forward hop-by-hop headers only
    excluded_headers = [
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade"
    ]
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in excluded_headers
    }

    return Response(
        generate_stream(),
        status=response.status_code,
        headers=response_headers,
        content_type=response.headers.get('Content-Type')
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=11434)