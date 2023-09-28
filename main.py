# pyinstaller --windowed --onefile --add-data="main.ui;." main.py

from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtCore import Qt, QTimer

import os
import sys
import threading
import datetime

import config
from core import BinanceCore


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), "main.ui"), self)

        # API
        self._binance_core = BinanceCore(
            config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY,
            self.api_load_margin_spin_box.value()
        )

        def change_api_load_margin():
            self._binance_core._api_load_margin = self.api_load_margin_spin_box.value() # noqa
        self.api_load_margin_spin_box.valueChanged.connect(
            change_api_load_margin
        )

        # LEVERAGES
        self._leverages_thread = None
        self._leverages = []
        self._leverages_updated = False
        self._leverages_last_updated_time = None
        self.update_leverages_btn.clicked.connect(self._update_leverages)

        def set_leverage_update_needed():
            self._leverages_updated = True
        self.leverages_max_leverage_spin_box.valueChanged.connect(
            set_leverage_update_needed
        )
        self.leverages_order_spin_box.valueChanged.connect(
            set_leverage_update_needed
        )

        # ORDERBOOKS
        self._orderbooks_thread = None
        self._orderbooks = []
        self._orderbooks_progress = (0, 0)
        self._orderbooks_last_updated_time = None
        self.update_orderbooks_btn.clicked.connect(self._update_orderbooks)
        self.orderbooks_blacklist_btn.clicked.connect(
            lambda: self._set_orderbooks_list(is_whitelist=False)
        )
        self.orderbooks_whitelist_btn.clicked.connect(
            lambda: self._set_orderbooks_list(is_whitelist=True)
        )

        fps = 60
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(int(1000 / fps))

    def _update_loop(self):
        # API INFO
        self.ping_lbl.setText(str(self._binance_core.ping))

        w, ma = self._binance_core.get_api_load()
        self.api_load_progress_bar.setMaximum(ma)
        self.api_load_progress_bar.setValue(w)
        self.api_load_progress_bar.setFormat(
            f"{w}/{ma}"
        )

        # LEVERAGES
        if self._leverages_thread is None or\
           not self._leverages_thread.is_alive():
            self.update_leverages_btn.setEnabled(True)
            self.update_leverages_btn.setText("Update")

        if self._leverages_updated:
            self._leverages_updated = False
            self.leverages_table.setRowCount(0)
            self.leverages_table.clearContents()
            self.leverages_table.setSortingEnabled(False)

            for i, leverage in enumerate(self._leverages):
                symbol = leverage["symbol"][:-4]
                bracket = list(filter(
                    lambda x: x["notionalCap"] > self.leverages_order_spin_box.value(),
                    leverage["brackets"]
                ))
                bracket = max(map(lambda x: x["initialLeverage"], bracket))
                bracket = min(bracket, self.leverages_max_leverage_spin_box.value())
                self.leverages_table.insertRow(i)
                self.leverages_table.setItem(
                    i, 0, QtWidgets.QTableWidgetItem(symbol)
                )
                bracket_item = QtWidgets.QTableWidgetItem()
                bracket_item.setData(Qt.EditRole, bracket)
                self.leverages_table.setItem(
                    i, 1, bracket_item
                )

            self.leverages_table.setSortingEnabled(True)

        # ORDERBOOKS
        if self._orderbooks_thread is None or\
           not self._orderbooks_thread.is_alive():
            self.update_orderbooks_btn.setEnabled(True)
            self.update_orderbooks_btn.setText("Update")

        if self._orderbooks_last_updated_time is not None:
            self.orderbooks_last_updated_time_lbl.setText(
                self._orderbooks_last_updated_time.strftime(
                    "%Y-%m-%d %H-%M-%S"
                )
            )
        else:
            self.orderbooks_last_updated_time_lbl.setText("-")

        self.orderbooks_update_progress_bar.setMaximum(
            self._orderbooks_progress[1]
        )
        self.orderbooks_update_progress_bar.setValue(
            self._orderbooks_progress[0]
        )
        self.orderbooks_update_progress_bar.setFormat(
            f"{self._orderbooks_progress[0]}/{self._orderbooks_progress[1]}"
        )

    def _update_leverages(self):
        self.update_leverages_btn.setEnabled(False)
        self.update_leverages_btn.setText("Wait...")
        f = None

        def f():
            info = self._binance_core.futures_exchange_info()
            trading_symbols = list(map(
                lambda x: x["symbol"], filter(
                    lambda x: x["status"] == "TRADING", # noqa
                    info["symbols"]
                )
            ))
            leverage_brackets = self._binance_core.futures_leverage_bracket()
            leverage_brackets = list(filter(
                lambda x: x["symbol"][-4:] == "USDT", leverage_brackets
            ))
            leverage_brackets = list(filter(
                lambda x: x["symbol"] in trading_symbols, leverage_brackets
            ))
            leverages = []
            for lb in leverage_brackets:
                leverages.append({
                    "symbol": lb["symbol"],
                    "brackets": lb["brackets"],
                })
            self._leverages = leverages
            self._leverages_updated = True

        self._leverages_thread = threading.Thread(target=f)
        self._leverages_thread.daemon = True
        self._leverages_thread.start()

    def _update_orderbooks(self):
        self.update_orderbooks_btn.setEnabled(False)
        self.update_orderbooks_btn.setText("Wait...")

        def os_t():
            info = self._binance_core.futures_exchange_info()
            symbols = info["symbols"]
            symbols = list(filter(
                lambda x: all([
                    x["quoteAsset"] == "USDT",
                    x["marginAsset"] == "USDT",
                    x["status"] == "TRADING"
                ]), symbols
            ))
            symbols = list(map(lambda x: x["baseAsset"] + "USDT", symbols))
            symbols = sorted(list(set(symbols)))
            # print(f"Доступных символов на бирже: {len(symbols)}")
            i = 0

            orderbooks = []
            try:
                for s in symbols:
                    depth = self._binance_core.futures_order_book(
                        symbol=s, limit=1000
                    )
                    orderbooks.append({"symbol": s, "depth": depth})
                    i += 1
                    self._orderbooks_progress = (i, len(symbols))
            except Exception:
                self._orderbooks_progress = (0, 0)

            self._orderbooks = orderbooks
            self._orderbooks_last_updated_time = datetime.datetime.now()

        self._orderbooks_thread = threading.Thread(target=os_t)
        self._orderbooks_thread.daemon = True
        self._orderbooks_thread.start()

    def _set_orderbooks_list(self, is_whitelist):
        symbols = []
        for orderbook in self._orderbooks:
            symbol = orderbook["symbol"]
            depth = orderbook["depth"]
            asks_min = min(list(map(lambda x: float(x[0]), depth["asks"])))
            bids_max = max(list(map(lambda x: float(x[0]), depth["bids"])))
            asks_qty = sum(list(map(
                lambda x: float(x[1]),
                filter(
                    lambda x: float(x[0]) <= asks_min * (1 + self.orderbooks_upper_percent.value() / 100), # noqa
                    depth["asks"]
                )
            )))
            bids_qty = sum(list(map(
                lambda x: float(x[1]),
                filter(
                    lambda x: float(x[0]) >= bids_max * (1 - self.orderbooks_bottom_percent.value() / 100), # noqa
                    depth["bids"]
                )
            )))
            asks_k = asks_qty * asks_min / 1000
            bids_k = bids_qty * bids_max / 1000
            if all([
                any([
                    self.orderbooks_upper_check_box.isChecked() and asks_k >= self.orderbooks_upper_volume.value(), # noqa
                    not self.orderbooks_upper_check_box.isChecked()
                ]),
                any([
                    self.orderbooks_bottom_check_box.isChecked() and bids_k >= self.orderbooks_bottom_volume.value(), # noqa
                    not self.orderbooks_bottom_check_box.isChecked()
                ]),
            ]):
                symbols.append(symbol)
            if not is_whitelist:
                all_symbols = list(map(lambda x: x["symbol"], self._orderbooks))
                symbols = sorted(list(set(all_symbols) - set(symbols)))

        symbols = list(map(lambda x: x[:-4], symbols))
        if len(symbols):
            self.orderbooks_symbols_count_lbl.setText(str(len(symbols)))
        else:
            self.orderbooks_symbols_count_lbl.setText("-")
        symbols = ",".join(symbols)
        self.orderbooks_symbols_list.setText(symbols)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()
