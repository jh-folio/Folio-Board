"""Allowlisted reader content, with no source attachments, machine paths or credentials."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from . import CaseError

# Keys used by stored structured readers. This is deliberately static: an owner
# adding an arbitrary new payload field does not opt it into personal retention.
STRUCTURED_KEYS = frozenset("""
schemaVersion methodVersion specVersion specSha256 instrumentId snapshotId id sourceId documentId artifactId artifactType
sourceLayer layer reuseAsEvidence market ticker providerSymbol name company title generatedAt createdAt recordedAt asOf date
source sourceRefs sourceLedger sources sourceVersion sourceState sourceAccessions sourceSha256 url accession accn form filed filingDate
status state reason code subCode message notice notices summary oneLineSummary beginnerSummary headline freshness
value values unit units currency currencies reporting quote quoteType precision decimals metric field label labels
start end period periodEnd periodYears fiscalYear year years rows observations observation metadata seriesId series_id
availableAt available_at vintage basis basisEvidence metaId meta_id fetchedAt fetched_at release_url released_at
kind identity cik corpCode exchange exchangeTimezone exchangeSource security listedSecurity listedUnit adsRatio adsBasisVerified
class classBasis classDiagnostics classValidation member memberLabels shareUnitBasis shareClassesSameEps listedClass
classificationInputs price fiscalYearPrices eventPriceChecks history shareEventSources dcfInputs returnAttributionInputs
priceFetchedAt riskFreeFetchedAt betaFetchedAt sessionDate provider close closes rawBars rawAmount rawValue rawCell
open high low adjClose dividend capitalGain amount dividendCoverage dividendListedUnit distributionEvents exDate exDateBasis recordDate
historyYears excludedYears excluded fiscalYearPrices sourceRows sourceField sourceAccessions sharesBasis periodEndSource
events eventDate eventDates eventSourceState providerEvents providerEvent shareEvents shareSource shareDate shareDateBasis
newSharesPerOldShare scheduledListingDate ratio ratioField quantity quantityField decreases decrease increase factor scale
normalizationDate normalizationFactor normalized unitDate unitBases unitProof unitValidation unitConversions
listedUnit unitInterval basisEvidence cells rowCells labels labelSources selection quote snippet evidence
state reason matched pairs before after dateBasis firstFiscalYear dividendBasis priceCheck priceChecks priceCoverage
beforeDate afterDate beforeClose afterClose eventProduct sameDayBasis sourceAccessions
beta riskFree taxRate debtCost debtPosition debtObservations debtTotal totalDebt netDebt cash cashConcept equityRiskPremium discountRate
baseFcf fcf fcfMargin ocf capexOut capexRaw sbc sbcBasis netIncome revenue revenuePerShare netMargin margin marginP50 marginN
currentMargin currentMarginPercentile currentPrice currentMarginPercentile pe peNow exitPE payout growth nearGrowth terminalGrowth
terminalShare terminal fadePath sensitivity projectionYears equityValue perShare incomeBasis borrowingsDefinition concept accountEvidence
normalizationDate priceBasis growthBasis growthWindow growthShare hasGrowthShare eps eps0 rps0 shares sharesRatio n
scenarios horizon irr irrFlat irrRange ranges conservative base optimistic support reasons notices adjusted
referenceFacts cashConversion dcf decomposition formula priceReturn returnParts contribution residual relativeError absoluteError
growth rerating earnings dividend total calculation response rawGrowth rawRerating rawDividend rawContribution rawTotal rawPriceReturn
rawDifference unroundedValue displayPriceReturn displayedValue rounding precision validation passed
startDate endDate startFiscalYear endFiscalYear startPeriodEnd endPeriodEnd startClose endClose startEps endEps startPE endPE
requestedYears endpoint endpoints current priorValues revisionId requiredReturn minMarginOfSafety holdingYears allowAboveHistoricalRange
createdAt snapshotId computedAt inputs results meta request start endExclusive interval autoAdjust backAdjust requestedStart requestedEnd
sourceState sourceFailureVerified sourceVersion identity stockDaily benchmarkDaily benchmark stock stock_code exchangeTimezoneName symbol
returnedStart returnedEnd coverageStart coverageEnd coverage complete priceSource dividendCoverage coverageEnd coverageStart
financialRates financialHolding industry ksicRevision code source checkedScope reasons uncertainty uncertainties counterEvidence contradictions
evidenceRole role usedInSections reliability axisKey researchQuestionId researchRound confidence docCount memoryCount quality score
dataGaps missingFields checkpoints nextCheckpoints criterion condition dueAt dueBy checkedAt item description severity
conditionResponse fieldPresence editSource kindAtWrite changeReason userStatedAt previousRevisionId contentHash revision content
core_thesis key_assumptions supporting_signals weakening_signals falsification_triggers next_checkpoints key_metrics linked_regimes
review_cycle conviction status source toleratedChanges nextCheck conditionState unknown unanswered skipped written legacy_unknown
deltaId reasonRevisionId verdict verdictLabel periodDays evidenceSource supportingEvidence challengingEvidence evidenceId
schemaVersion sourceSchemaVersion reviewRevision date reviewState reviewedAt generatedAt inputBasis capturedAt fingerprint
positionReviews positionRoster portfolioRisks sharedExposures quantitativeRiskSignals reviewReasons dueCheckpoints canonicalReferences
thesisPresent latestReviewPresent thesisVerdict riskKey weight baseCurrency concentration maxHolding top3 top5 status
coverage totalPositionCount rosterIncludedCount detailIncludedCount omittedRosterCount omittedDetailCount reportSelection
candidateCount includedCount excludedCount type key tickers stateId stateKey momentum marketStateRef marketStates
marketRegime keyDrivers watchItems marketViews us kr jp europe headline oneLineSummary counterEvidence uncertainties
profileId items factor direction magnitudeBasis sourceRefs dataGaps interpretation observations freshnessReason
requiredReturn minMarginOfSafety holdingYears allowAboveHistoricalRange criteria criteriaRevisionId blockingReasons warnings state
scopeCopy evaluatedAt instrumentType view snapshotId priceSnapshotId methodVersion known available unknown unavailable met unmet
reviewRows seq snapshot_id detected_by_snapshot_id fiscal_year created_at metric reason source_hash
topicKey topicLabel deepResearch reportType topicPlan candidateTickers researchQuestions timeHorizon marketScope
revisionBasis revisionProof fromSpecSha256 toSpecSha256 detectedBySnapshotId reviewNeeded reasonCodes
max min p50 p75 percentile percentiles distribution count window windows startYear endYear growthWindowYears
endEps startEps endPE startPE display percentage percent displayValue precision yearsUsed five ten
snapshot returnAttribution dimensions basis dataGaps sourceRefs states marketState profile level axis promotion promotionDecisionId
cycleSignal cycleSignalPromotion cycleSignalPromotionDecisionId cycleSignalBasis cycleCorroboration conditions W K R Q
inputFingerprint trend direction indexValue change recentPeriods details observations inputs metadata missingSeries
configured allow aboveSample axes needed sampleMin sampleMax aboveHistoricalRange highPremise neededValue requiredMargin
5 10 M S annual basisRefs breakEvenMargin breakEvenPE delta disclosedEps epsFromRevenue epsGap from g input intrinsicValue
marginOfSafetyJudgment marginPercentile marginRange monthsBeforeSession nextChecks noGrowth normEps notes p25 readiness
recentEps recentWindow result reverse rpsGrowth scope to cashDividends continuityBasis snapshotShareUnitDate annualPeriods
index difference previousDate impliedDividend requestedDate requestedStartDate requestedEndDate priceDate
unknownReason conflicts evidenceStage observationSelection ruleParameters structuralVulnerability availabilityBasis
conflict metadataId vintageDate limitations section extractionVersion financialContext unknownCount dataGap comparisonPeriod exposureId
diagnosticOnly thetaC thetaR yearOverYear previousYearOverYear changePercentagePoints rowKind firstSeenAt version
overall marketInterpretation directionLabel directionTone marketImpact nextMemoryCheck evidenceSummary whyItMatters
sourceRef transformVersion selectedPeriod observationMonth
scoredPassages exposures omittedFragments
ownershipBasisVersion originalDecisions journalId bodyHash caseId
""".split())

REPORT_FIELDS = frozenset({"id", "title", "generatedAt", "createdAt", "date", "company", "markdown", "sourceLedger",
                           "sourceRefs", "sources", "dataGaps", "counterEvidence", "uncertainties", "quality", "checkpoints",
                           "topicKey", "topicLabel", "reportType", "deepResearch", "topicPlan"})
REASON_FIELDS = frozenset({"revisionId", "ticker", "revision", "previousRevisionId", "contentHash", "content", "conditionResponse",
                           "fieldPresence", "editSource", "kindAtWrite", "changeReason", "userStatedAt", "basisRefs", "recordedAt"})
PATH_OR_SECRET = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|file://|\\\\[^\s\\]+\\|/(?:Users|home|tmp|mnt|var|etc)/|"
    r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|\bAKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC )?PRIVATE KEY|"
    r"\b(?:api[_ -]?key|access[_ -]?token|password|authorization)\s*[:=]\s*\S+)", re.I
)
URL_PATTERN = re.compile(r"https?://[^\s<>\]\)\"']+", re.I)
SECRET_QUERY = re.compile(r"(?:[?&])(?:api_?key|token|access_?token|secret|password)=", re.I)


def check_text(value):
    if PATH_OR_SECRET.search(value):
        raise CaseError("sensitive_content_requires_exclusion")
    for match in URL_PATTERN.finditer(value):
        try:
            parsed = urlsplit(match[0])
            if parsed.username is not None or parsed.password is not None or SECRET_QUERY.search(match[0]):
                raise CaseError("sensitive_content_requires_exclusion")
        except ValueError:
            raise CaseError("unsafe_source_url") from None
    return value


def safe_content(value, *, allowed=None, omitted=None, location="", depth=0):
    """Preserve allowed values exactly; exclusions are field names, never values."""
    if depth > 30:
        raise CaseError("source_structure_too_deep")
    if isinstance(value, str):
        return check_text(value)
    if isinstance(value, list):
        return [safe_content(v, omitted=omitted, location=location, depth=depth + 1) for v in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            dynamic_key = allowed is None and (
                re.fullmatch(r"(?:19|20)\d{2}(?:-\d{2}-\d{2})?", key)
                or (location == "observationSelection" and re.fullmatch(
                    r"commonMonth:(?:US|KR)|latest:[A-Z][A-Z0-9_]{0,39}|krCycleMonth|spreadPeriods", key)))
            if key not in (allowed if allowed is not None else STRUCTURED_KEYS) and not dynamic_key:
                if omitted is not None:
                    # Unknown keys may themselves contain sensitive strings. A count
                    # explains partial preservation without leaking those names.
                    omitted.append(1)
                continue
            if key == "url" and item:
                if not isinstance(item, str) or urlsplit(item).scheme.lower() not in {"http", "https"} or not urlsplit(item).netloc:
                    if omitted is not None:
                        omitted.append(1)
                    continue
            result[key] = safe_content(item, omitted=omitted, location=key, depth=depth + 1)
        return result
    if value is None or type(value) in {bool, int, float}:
        return value
    raise CaseError("source_value_invalid")


def preserve(value, *, allowed=None):
    omitted = []
    body = safe_content(value, allowed=allowed, omitted=omitted)
    return body, {"kind": "reader_fields", "omittedFieldCount": len(omitted), "attachmentsPreserved": False}
