import requests
from requests.adapters import HTTPAdapter


class RESTClient:
    def __init__(self, host, port, timeout=30, pool_connections=10, pool_maxsize=100):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, endpoint, params=None):
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint, data=None):
        return self._request("POST", endpoint, json=data)

    def put(self, endpoint, data=None):
        return self._request("PUT", endpoint, json=data)

    def delete(self, endpoint, params=None):
        return self._request("DELETE", endpoint, params=params)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"{method} Request error: {e}")
            return None

    def close(self):
        self.session.close()