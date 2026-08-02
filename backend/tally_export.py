"""Tally/Busy XML export (B2).

Tally's own import path is XML, not CSV — a CSV export just pushes the
column-mapping problem onto the accountant, which defeats the point of
shipping an export at all for CA gatekeeping. This produces the standard
`<ENVELOPE>` voucher-import structure Tally expects on `Gateway of Tally >
Import Data`.

Covers, for a date range: sales, purchases (deliveries — goods coming in),
returns (sales_return), credit notes, debit notes, and payments received.
Stock-neutral money-only types (credit_note, debit_note) and the stock-only
opening_balance/stock_take/adjustment types are handled per the frozen
foundation contract in ledger.py — this module only reads events, it never
replays or reorders them.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

_VOUCHER_TYPE = {
    "sale": "Sales",
    "delivery": "Purchase",
    "sales_return": "Credit Note",
    "credit_note": "Credit Note",
    "debit_note": "Debit Note",
}

_EXPORTED_EVENT_TYPES = tuple(_VOUCHER_TYPE)


def _tally_date(occurred_on: str) -> str:
    """Tally wants YYYYMMDD with no separators."""
    return str(occurred_on or "").replace("-", "")[:8]


def _party_name(event: dict, customers_by_id: dict) -> str:
    cid = event.get("customer_id")
    if cid and cid in customers_by_id:
        return customers_by_id[cid].get("name") or "Cash Customer"
    return "Cash Customer"


def _amount(event: dict, catalogue_by_id: dict) -> float:
    qty = float(event.get("qty") or 0)
    rate = event.get("quoted_rate") if event.get("quoted_rate") is not None else event.get("rate")
    rate = float(rate or 0)
    return round(qty * rate, 2)


def _voucher_xml(event: dict, catalogue_by_id: dict, customers_by_id: dict) -> str:
    vch_type = _VOUCHER_TYPE.get(event["type"], "Journal")
    date_ = _tally_date(event.get("occurred_on"))
    voucher_no = escape(str(event.get("event_id", "")))
    party = escape(_party_name(event, customers_by_id))
    sku = catalogue_by_id.get(event.get("sku_id"), {})
    item_name = escape(sku.get("canonical") or event.get("sku_id") or "")
    amount = _amount(event, catalogue_by_id)
    qty = event.get("qty")
    unit = escape(str(event.get("unit") or ""))
    # Sales/returns/notes credit the party for money owed to the shop (Sales,
    # Credit Note against a sale) or debit it (Debit Note, Purchase); the sign
    # convention below matches Tally's ledger-entry expectation of a signed
    # amount on ALLLEDGERENTRIES.LIST, not accounting-grade double entry.
    is_deemed_positive = "Yes" if vch_type in ("Purchase", "Debit Note") else "No"
    return f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="{escape(vch_type)}" ACTION="Create">
        <DATE>{date_}</DATE>
        <VOUCHERTYPENAME>{escape(vch_type)}</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{voucher_no}</VOUCHERNUMBER>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <ALLINVENTORYENTRIES.LIST>
          <STOCKITEMNAME>{item_name}</STOCKITEMNAME>
          <ACTUALQTY>{qty}{(" " + unit) if unit else ""}</ACTUALQTY>
          <BILLEDQTY>{qty}{(" " + unit) if unit else ""}</BILLEDQTY>
          <AMOUNT>{amount}</AMOUNT>
        </ALLINVENTORYENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>{is_deemed_positive}</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>"""


def _payment_voucher_xml(payment: dict, customers_by_id: dict) -> str:
    date_ = _tally_date(payment.get("paid_on"))
    voucher_no = escape(str(payment.get("payment_id", "")))
    cid = payment.get("customer_id")
    party = escape((customers_by_id.get(cid) or {}).get("name") or "Cash Customer")
    amount = round(float(payment.get("amount") or 0), 2)
    return f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Receipt" ACTION="Create">
        <DATE>{date_}</DATE>
        <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{voucher_no}</VOUCHERNUMBER>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>"""


def build_tally_xml(*, events: list, payments: list, catalogue_by_id: dict,
                    customers_by_id: dict) -> str:
    """`events` and `payments` are pre-filtered to the requested date range —
    this module makes no date decisions of its own."""
    vouchers = [
        _voucher_xml(e, catalogue_by_id, customers_by_id)
        for e in events if e.get("type") in _EXPORTED_EVENT_TYPES
    ]
    vouchers += [_payment_voucher_xml(p, customers_by_id) for p in payments]
    body = "\n".join(vouchers)
    return f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
      </REQUESTDESC>
      <REQUESTDATA>
{body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>
"""
