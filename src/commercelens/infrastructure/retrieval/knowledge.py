"""Small lexical BM25 index over curated business interpretation notes."""

from collections import Counter
from math import log
import re

from commercelens.application.contracts import Citation


DOCUMENTS = (
    Citation("delivery-eligibility", "Late delivery and cohort eligibility",
             "Filter purchase_date for the cohort. is_late is null for orders outside delivered orders with both "
             "delivery dates. Divide late orders by count(is_late). Estimated delivery uses a calendar date. "
             "delivery_days measures observed elapsed days from purchase."),
    Citation("seller-attribution", "Seller participation and contribution",
             "seller_orders contains one row per order and seller. Multi-seller orders can appear for several "
             "sellers. Changes in late-delivery contribution are accounting comparisons. Order-level delivery "
             "cannot identify the seller responsible or establish causation."),
    Citation("review-association", "Delivery and review score",
             "Order review_score averages scores within each order. Compare is_late true and false after excluding "
             "null delivery status and missing review scores. Observational differences cannot establish cause."),
    Citation("payment-grain", "Payment proxy and order grain",
             "orders.payment_value already sums recorded payments to one row per order. Includes all order statuses "
             "and any recorded freight. Avoid a sum over joined item rows. The sample cannot establish net revenue, "
             "profit, refunds, gross margin or marketing attribution."),
    Citation("category-value", "Merchandise value and category",
             "Use sum(items.price) for product category or seller value. Freight is excluded. Use count(distinct "
             "order_id) for orders within a category. Categories may overlap at order grain."),
    Citation("change-contribution", "Period comparison and group contributions",
             "Use comparable half-open purchase windows. Additive contribution is current minus baseline group value. "
             "For rate change contributions divide each group's numerator by the overall eligible population in "
             "each period, then subtract baseline from current. A group contribution is not a causal effect."),
    Citation("sample-scope", "Population and unavailable fields",
             "The Olist sample uses proportional sampling by purchase month. Sample totals describe sampled orders "
             "only. No inventory, logistics carrier, ad spend, product cost, refund or external weather fields."),
)


def tokens(value: str) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", value.lower())
    return [word[:-1] if len(word) > 4 and word.endswith("s") else word for word in terms if len(word) > 2]


class Knowledge:
    def __init__(self):
        self.terms = [Counter(tokens(f"{doc.title} {doc.excerpt}")) for doc in DOCUMENTS]
        self.average_length = sum(map(Counter.total, self.terms)) / len(self.terms)
        self.frequency = Counter(term for document in self.terms for term in document)

    def search(self, question: str, limit: int = 3) -> list[Citation]:
        def score(document):
            norm = 1.2 * (0.25 + 0.75 * document.total() / self.average_length)
            return sum(
                log(1 + (len(self.terms) - self.frequency[term] + 0.5) / (self.frequency[term] + 0.5))
                * document[term] * 2.2 / (document[term] + norm)
                for term in set(tokens(question)) if term in document
            )

        ranked = sorted(zip(map(score, self.terms), DOCUMENTS), key=lambda item: (-item[0], item[1].id))
        return [document for relevance, document in ranked[:limit] if relevance > 0]
