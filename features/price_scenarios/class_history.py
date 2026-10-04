"""Annual listed-class inline XBRL facts. Pure parsing and conservative validation."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import re
import unicodedata
from bs4 import BeautifulSoup

from .coverage_history import EPS, SHARES, INCOME, THRESHOLD, observations, row_at, same_period, source_fact
from .decimal_ops import number
from .history import _annual_period

METRICS = {"EarningsPerShareDiluted": EPS, "WeightedAverageNumberOfDilutedSharesOutstanding": SHARES,
           "CommonStockDividendsPerShareDeclared": "DPS"}
MAX_CLASS_FILINGS = 8


def _empty_amendment(packet, soup, ns):
    """Positive amendment-only evidence; absence of inline alone proves nothing."""
    if packet.get('form') != '10-K/A' or not soup.find('html') or not soup.find('body'):
        return False
    for fact in soup.find_all(['ix:nonfraction', 'ix:fraction']):
        prefix = fact.get('name', '').split(':')[0]
        namespace = str(ns.get(prefix, ''))
        if not namespace.startswith('http://xbrl.sec.gov/dei/'):
            return False  # unknown or malformed financial facts are not absent
        unit = soup.find('xbrli:unit', id=fact.get('unitref')) if fact.get('unitref') else None
        if unit and unit.find('xbrli:measure', string=re.compile(r'^iso4217:')) and 'dei' not in namespace:
            return False
    text = soup.get_text(' ', strip=True)
    if re.search(r'\b(?:consolidated\s+)?(?:balance\s+sheets?|statements?\s+of\s+(?:income|earnings|equity|comprehensive\s+income|operations|cash\s+flows|financial\s+position))\b', text, re.I):
        return False
    for table in soup.find_all('table'):
        remaining = deepcopy(table)
        for fact in remaining.find_all(['ix:nonfraction', 'ix:fraction', 'ix:nonnumeric']):
            if str(ns.get(fact.get('name', '').split(':')[0], '')).startswith('http://xbrl.sec.gov/dei/'):
                fact.decompose()  # confirmed cover/company facts are not financials
        if re.search(r'\d', remaining.get_text()):
            return False  # unclassified plain numeric tables are not proof of absence
    # Explicit limited-scope disclosure is required even for DEI-only inline.
    return bool(re.search(r'\b(?:sole(?:ly)?|only|exclusively)\b.{0,300}\bPart\s+III\b', text, re.I | re.S)
                or re.search(r'\b(?:does\s+not|no)\b.{0,100}\b(?:amend|change|revise|updated?|financial\s+statements)\b.{0,100}\bfinancial\s+statements\b', text, re.I | re.S))


def covered_class_years(rows, as_of):
    pairs = {}
    for row in rows:
        if row.get('error') or row['period']['end'] > as_of or row['metric'] not in {EPS, SHARES}:
            continue
        key = (row['fiscalYear'], row['filed'], row['accession'], row['period']['start'], row['period']['end'], row['member'])
        pairs.setdefault(key, set()).add(row['metric'])
    return {key[0] for key, metrics in pairs.items() if metrics == {EPS, SHARES}}


def listed_class(security):
    if security.get("kind") != "common_share":
        return None
    matches = re.findall(r"\bclass\s+([a-z0-9]+(?:-[a-z0-9]+)?)\s+(?:common|ordinary|capital)\s+(?:stock|shares?)\b",
                         unicodedata.normalize("NFKC", security.get("title", "")), re.I)
    ids = {m.upper() for m in matches}
    return {"id": next(iter(ids)), "label": "Class " + next(iter(ids))} if len(ids) == 1 else None


def _namespaces(soup):
    return {key.removeprefix("xmlns:"): value for tag in soup.find_all(True)
            for key, value in tag.attrs.items() if key.startswith("xmlns:")}


def _standard(name, ns, local):
    parts = name.split(":", 1)
    return len(parts) == 2 and parts[1] == local and str(ns.get(parts[0], "")).startswith("http://fasb.org/us-gaap/")


def _member_matches(member, ns, identity, labels):
    prefix, sep, local = member.partition(":")
    if not sep or prefix not in ns:
        return False
    if str(ns[prefix]).startswith("http://fasb.org/us-gaap/"):
        return local == "CommonClass" + identity["id"] + "Member"
    for label in labels.get(member, []):
        clean = re.sub(r"\s*\[Member\]\s*$", "", str(label), flags=re.I).strip()
        match = re.fullmatch(r"Class\s+([a-z0-9]+(?:-[a-z0-9]+)?)\s+(?:Common|Ordinary|Capital)\s+(?:Stock|Shares?)", clean, re.I)
        if match and match[1].upper() == identity["id"]:
            return True
    return False


def _unit(unit, currency):
    if unit is None:
        return None
    numerator, denominator = unit.find("xbrli:unitnumerator"), unit.find("xbrli:unitdenominator")
    if numerator and denominator:
        a, b = [m.get_text(strip=True) for m in numerator.find_all("xbrli:measure")], [m.get_text(strip=True) for m in denominator.find_all("xbrli:measure")]
        return currency + "/shares" if a == ["iso4217:" + currency] and b == ["xbrli:shares"] else None
    measures = [m.get_text(strip=True) for m in unit.find_all("xbrli:measure")]
    return "shares" if measures == ["xbrli:shares"] else currency if measures == ["iso4217:" + currency] else None


def _numeric(fact):
    """SEC dot-decimal transforms only; unknown transforms never silently coerce."""
    displayed = fact.get_text("", strip=True)
    fmt = fact.get("format", "").split(":")[-1]
    text = displayed.replace("\u00a0", "").replace(" ", "")
    if fmt in {"num-dot-decimal", "numcommadot", "numdotdecimal"}:
        if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
            raise ValueError("invalid_inline_number")
        text = text.replace(",", "")
    elif fmt in {"zerodash", "numdash", "fixed-zero"} and text in {"-", "—", "–"}:
        text = "0"
    elif fmt or not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError("unsupported_inline_transform")
    scale = int(fact.get("scale", "0"))
    if not -20 <= scale <= 20 or fact.get("sign") not in {None, "-"}:
        raise ValueError("invalid_inline_scale_sign")
    value = number(text) * Decimal(10) ** scale
    if fact.get("sign") == "-":
        value = -value
    decimals = fact.get("decimals")
    precision = max(0, -value.as_tuple().exponent) if decimals == "INF" else int(decimals)
    if not -20 <= precision <= 20:
        raise ValueError("invalid_inline_decimals")
    return str(value), precision, displayed


def read_class_filing(packet, security, *, cik, currency):
    """Read facts and invalid observations BEFORE choosing latest submitted years."""
    identity = listed_class(security)
    if identity is None:
        return {"reason": "listed_class_eps_not_found", "rows": []}
    soup = BeautifulSoup(packet.get("markup", ""), "html.parser")
    ns = _namespaces(soup)
    if _empty_amendment(packet, soup, ns):
        return {'reason': None, 'rows': [], 'skip': True}
    if not soup.find('ix:nonfraction'):
        return {'reason': 'listed_class_source_unavailable', 'rows': []}
    contexts, members = {}, set()
    for ctx in soup.find_all("xbrli:context"):
        entity = ctx.find("xbrli:identifier")
        start, end = ctx.find("xbrli:startdate"), ctx.find("xbrli:enddate")
        dims, typed = ctx.find_all("xbrldi:explicitmember"), ctx.find_all("xbrldi:typedmember")
        if (not entity or not start or not end or len(dims) != 1 or typed
                or not _standard(dims[0].get("dimension", ""), ns, "StatementClassOfStockAxis")
                or str(entity.get("scheme", "")).rstrip("/") != "http://www.sec.gov/CIK"):
            continue
        try:
            same_entity = int(entity.get_text(strip=True)) == int(cik)
        except (ValueError, TypeError):
            same_entity = False
        period = {"start": start.get_text(strip=True), "end": end.get_text(strip=True)}
        member = dims[0].get_text(strip=True)
        if same_entity and _annual_period(period["start"], period["end"]) and _member_matches(member, ns, identity, packet.get("labels") or {}):
            contexts[ctx["id"]] = {"period": period, "member": member, "axis": dims[0]["dimension"]}
    facts = [f for f in soup.find_all("ix:nonfraction") if f.get("contextref") in contexts
             and any(_standard(f.get("name", ""), ns, c) for c in METRICS)]
    members = {contexts[f["contextref"]]["member"] for f in facts if f["name"].split(":")[-1] in METRICS}
    if len(members) != 1:
        return {"reason": "listed_class_eps_ambiguous" if len(members) > 1 else "listed_class_eps_not_found", "rows": []}
    units = {u["id"]: u for u in soup.find_all("xbrli:unit")}
    rows = []
    for fact in facts:
        ctx = contexts[fact["contextref"]]
        metric = METRICS[fact["name"].split(":")[-1]]
        row = {"metric": metric, "fiscalYear": int(ctx["period"]["end"][:4]), **deepcopy(ctx),
               "filed": packet["filed"], "accession": packet["accession"], "form": packet["form"],
               "url": packet["url"], "context": fact["contextref"], "concept": fact["name"],
               "source": "filing_class_member", "classBasis": identity["id"], "priorValues": [],
               "memberLabels": deepcopy((packet.get("labels") or {}).get(ctx["member"], [])),
               "labelSources": deepcopy(packet.get("labelSources") or []),
               "scale": fact.get("scale", "0"), "sign": fact.get("sign"), "decimals": fact.get("decimals"),
               "displayedValue": fact.get_text("", strip=True)}
        try:
            value, precision, displayed = _numeric(fact)
            unit = _unit(units.get(fact.get("unitref")), currency)
            expected = "shares" if metric == SHARES else currency + "/shares"
            if unit != expected or fact.get("xsi:nil") in {"true", "1"}:
                raise ValueError("inline_unit_unknown")
            row.update(value=value, precision=precision, displayedValue=displayed, unit=unit)
        except (ValueError, TypeError, ArithmeticError):
            row["error"] = "listed_class_source_unavailable"
        rows.append(row)
    return {"rows": rows, "identity": identity,
            "reason": "listed_class_source_unavailable" if any(r.get('error') for r in rows) else None}


def supplement_class_history(history, filings, security, *, cik, as_of):
    """Inject only a latest-year-valid, three-year-validated listed-class history."""
    out = deepcopy(history)
    years = sorted({int(r["fiscalYear"]) for r in history["rows"]})
    if not years or row_at(history, EPS, years[-1]) or listed_class(security) is None:
        return out
    diagnostic = {"status": "unavailable", "reason": "listed_class_source_unavailable", "years": []}
    out["classDiagnostics"] = diagnostic
    chosen = sorted([p for p in filings if p.get("filed", "") <= as_of and p.get("form") in {"10-K", "10-K/A"}],
                    key=lambda p: (p["filed"], p["accession"]), reverse=True)
    chosen = list({p['accession']: p for p in reversed(chosen)}.values())
    chosen = sorted(chosen, key=lambda p: (p['filed'], p['accession']), reverse=True)[:MAX_CLASS_FILINGS]
    if not chosen:
        return out
    by_year, parsed_all = {}, []
    for packet in chosen:
        entry = {'accession': packet['accession'], 'filed': packet['filed'], 'form': packet['form'],
                 'sourceSha256': hashlib.sha256(packet.get('markup', '').encode('utf-8')).hexdigest()}
        diagnostic.setdefault('filings', []).append(entry)
        if not packet.get("markup"):
            entry.update(action='stop', reason='listed_class_source_unavailable')
            break  # keep verified newer years; never fall through to an older substitute
        parsed = read_class_filing(packet, security, cik=cik, currency=history.get("currency", ""))
        if parsed.get('skip'):
            entry.update(action='skip', reason='amendment_without_financials')
            continue
        if parsed["reason"]:
            diagnostic["reason"] = parsed["reason"]
            entry.update(action='stop', reason=parsed['reason'])
            break
        entry.update(action='read', reason=None)
        parsed_all.extend(parsed["rows"])
        for row in parsed["rows"]:
            if row["fiscalYear"] in years and row["period"]["end"] <= as_of:
                by_year.setdefault(row["fiscalYear"], packet["accession"])
        if set(years) <= covered_class_years(parsed_all, as_of):
            diagnostic['stopReason'] = 'window_covered'
            break
    diagnostic.setdefault('stopReason', 'format_stop' if diagnostic['filings'][-1]['action'] == 'stop'
                          else 'filing_limit' if len(chosen) == MAX_CLASS_FILINGS else 'no_more_filings')
    accepted, preserved = [], []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year, accession in sorted(by_year.items()):
            group = [r for r in parsed_all if r["fiscalYear"] == year and r["accession"] == accession]
            reason = None
            pair = {}
            for metric in (EPS, SHARES, "DPS"):
                matches = [r for r in group if r["metric"] == metric]
                if any(r.get("error") for r in matches):
                    reason = "listed_class_source_unavailable"
                elif len({(r["value"], r["unit"], r["period"]["start"], r["period"]["end"], r["member"]) for r in matches}) > 1:
                    reason = "listed_class_eps_ambiguous"
                elif matches:
                    pair[metric] = min(matches, key=lambda r: r["precision"])
            e, s, income = pair.get(EPS), pair.get(SHARES), row_at(history, INCOME, year)
            if not e or not s:
                reason = reason or "listed_class_eps_not_found"
            elif not same_period(e, s, income) or number(s["value"]) <= 0 or income["unit"] != history["currency"]:
                reason = reason or "listed_class_reconciliation_failed"
            elif income.get('scope') not in {None, 'company_consolidated'}:
                reason = reason or "listed_class_reconciliation_failed"
            validation = None
            if not reason:
                quotient = number(income["value"]) / number(s["value"])
                eps = number(e["value"])
                error = abs(quotient - eps)
                validation = {"netIncome": source_fact(income), "shares": source_fact(s), "eps": source_fact(e),
                              "quotient": str(quotient), "absoluteError": str(error), "threshold": str(THRESHOLD),
                              "relativeError": str(error / abs(eps)) if eps else None,
                              "incomeBasis": "company_consolidated_no_allocation"}
                if error > THRESHOLD * abs(eps):
                    reason = "listed_class_reconciliation_failed"
            # A dimensionless/class transition needs official confirmation of the same basis.
            old_pair = {m: row_at(history, m, year) for m in pair}
            if not reason and any(r and not r.get("derived") and r.get("classBasis") != e["classBasis"] for r in old_pair.values()):
                reason = "listed_class_eps_ambiguous"
            if not reason and any(r and not r.get("derived") and r["accession"] == accession
                                  and abs(number(r["value"]) - number(pair[m]["value"])) > max(
                                      Decimal("0.5") * Decimal(10) ** -r["precision"],
                                      Decimal("0.5") * Decimal(10) ** -pair[m]["precision"])
                                  for m, r in old_pair.items()):
                reason = "listed_class_eps_ambiguous"
            if not reason and any(r and (r.get("filed", ""), r.get("accession", "")) > (e["filed"], e['accession']) for r in old_pair.values()):
                # No verified same-filing class pair for the newer dimensionless source.
                newer_eps, newer_shares = old_pair.get(EPS), old_pair.get(SHARES)
                if not newer_eps or not newer_shares or (newer_eps["filed"], newer_eps["accession"]) != (newer_shares["filed"], newer_shares["accession"]):
                    reason = "listed_class_eps_ambiguous"
                else:
                    if not same_period(newer_eps, newer_shares, income) or number(newer_shares["value"]) <= 0:
                        reason = "listed_class_reconciliation_failed"
                    else:
                        quotient = number(income["value"]) / number(newer_shares["value"])
                        if abs(quotient - number(newer_eps["value"])) > THRESHOLD * abs(number(newer_eps["value"])):
                            reason = "listed_class_reconciliation_failed"
                        else:
                            pair.update({EPS: deepcopy(newer_eps), SHARES: deepcopy(newer_shares)})
                            error = abs(quotient - number(newer_eps['value']))
                            validation = {'netIncome': source_fact(income), 'shares': source_fact(newer_shares), 'eps': source_fact(newer_eps),
                                          'quotient': str(quotient), 'absoluteError': str(error), 'threshold': str(THRESHOLD),
                                          'relativeError': str(error / abs(number(newer_eps['value']))) if number(newer_eps['value']) else None,
                                          'incomeBasis': 'company_consolidated_no_allocation'}
            diagnostic["years"].append({"fiscalYear": year, "reason": reason, "validation": validation})
            if not reason:
                for metric, row in pair.items():
                    # Preserve all prior actual class filings for share-event proof.
                    earlier = [r for r in parsed_all if r["metric"] == metric and r["fiscalYear"] == year
                               and not r.get("error") and r["period"] == row["period"]
                               and (r["filed"], r["accession"]) < (row["filed"], row["accession"])]
                    row = deepcopy(row)
                    row["priorValues"] = sorted(earlier, key=lambda r: (r["filed"], r["accession"]))
                    row["classValidation"] = deepcopy(validation)
                    accepted.append(row)
                    old = row_at(history, metric, year)
                    if old:
                        preserved.append(deepcopy(old))
    valid = {r["fiscalYear"] for r in accepted if r["metric"] == EPS}
    if len(valid) < 3 or years[-1] not in valid:
        failures = [d["reason"] for d in diagnostic["years"] if d["reason"] and d["fiscalYear"] == years[-1]]
        diagnostic["reason"] = failures[0] if failures else diagnostic['reason']
        return out
    keys = {(r["metric"], r["fiscalYear"]) for r in accepted}
    rejected = {d['fiscalYear'] for d in diagnostic['years'] if d['reason']}
    discarded = [r for r in history['rows'] if r['metric'] in {EPS, SHARES, 'DPS'} and r['fiscalYear'] in rejected]
    out["rows"] = sorted([r for r in history["rows"] if (r["metric"], r["fiscalYear"]) not in keys and r not in discarded] + accepted,
                         key=lambda r: (r["fiscalYear"], r["metric"], r["period"]["end"]))
    out["existingSourceRows"] = preserved + deepcopy(discarded)
    out["listedClass"] = listed_class(security)
    diagnostic.update(status="available", reason=None)
    return out
