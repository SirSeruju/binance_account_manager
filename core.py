from binance.client import Client
import time
import datetime
import threading
import traceback


class BinanceCore:
    def __init__(self, api_key, api_secret, api_load_margin=400):
        self._client = Client(api_key=api_key, api_secret=api_secret)

        self._api_load_margin = api_load_margin

        self._info = self._client.futures_exchange_info()
        self._last_response_time = datetime.datetime.now()

        self._update_thread = threading.Thread(
            target=self._core_update_loop
        )
        self._update_thread.daemon = True
        self._update_thread.start()

        def factory(name):
            def f(*args, **kwargs):
                self._wait_reset()
                resp = getattr(self._client, name)(*args, **kwargs)
                if name == "futures_exchange_info":
                    self._info = resp
                self._last_response_time = datetime.datetime.now()
                return resp
            return f
        for p in list(filter(
            lambda x: "futures" in x and x[0] != "_", dir(self._client)
        )):
            setattr(self, p, factory(p))

    def get_api_load(self):
        w = 0
        if self._client.response:
            w = int(self._client.response.headers["x-mbx-used-weight-1m"])
        return (w, int(self._info["rateLimits"][0]["limit"]))

    def _wait_reset(self):
        c = self._client
        api_limit = int(self._info["rateLimits"][0]["limit"])
        if int(c.response.headers["x-mbx-used-weight-1m"]) > api_limit - self._api_load_margin: # noqa
            w = (self._last_response_time.timestamp() // 60 + 1) * 60
            wt = w - datetime.datetime.now().timestamp()
            if wt > 0:
                time.sleep(wt)

    @property
    def ping(self):
        if self._client.response:
            return int(self._client.response.elapsed.total_seconds() * 1000)
        else:
            return 9999999

    def _core_update_loop(self):
        while True:
            try:
                self._client.futures_ping()
            except Exception:
                print(traceback.format_exc())
            time.sleep(1)
