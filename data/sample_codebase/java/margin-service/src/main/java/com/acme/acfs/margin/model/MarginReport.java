package com.acme.acfs.margin.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * The output of a single daily margin run for one venue.
 *
 * <p>A report corresponds to one row in {@code margin_runs} plus the
 * per-client rows in {@code margin_results}. Run identifiers follow the
 * corpus convention {@code MR-YYYYMMDD-{venue}}, for example
 * {@code MR-20240315-SGX}. All amounts are expressed in the venue's base
 * currency.
 */
public record MarginReport(
        String runId,
        LocalDate runDate,
        Venue venue,
        List<ClientMarginResult> clientResults) {

    /** Per-client margin figures produced by a margin run. */
    public record ClientMarginResult(
            String clientId,
            BigDecimal initialMargin,
            BigDecimal variationMargin) {

        /** Returns the total margin requirement for the client. */
        public BigDecimal totalMargin() {
            return initialMargin.add(variationMargin);
        }
    }

    /** Returns the venue currency used for all amounts in this report. */
    public Currency currency() {
        return venue.baseCurrency();
    }

    /** Returns the sum of initial margin across all clients in the run. */
    public BigDecimal totalInitialMargin() {
        return clientResults.stream()
                .map(ClientMarginResult::initialMargin)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    /** Returns the sum of variation margin across all clients in the run. */
    public BigDecimal totalVariationMargin() {
        return clientResults.stream()
                .map(ClientMarginResult::variationMargin)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
