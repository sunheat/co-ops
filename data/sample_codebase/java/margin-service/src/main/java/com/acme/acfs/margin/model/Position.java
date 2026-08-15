package com.acme.acfs.margin.model;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * A client-level position held for a venue and instrument.
 *
 * <p>Positions are maintained by the nightly batch and stored in the
 * {@code positions} table. They are the primary input to
 * {@code MarginCalculator} and are aggregated by {@code ReconciliationService}
 * for comparison against venue-published aggregate positions.
 *
 * <p>Manual position adjustments made by operations analysts are a known
 * source of reconciliation breaks and must always be recorded with an audit
 * trail.
 */
public record Position(
        String clientId,
        Venue venue,
        String instrument,
        long quantity,
        BigDecimal lastPrice,
        BigDecimal previousClose,
        LocalDate asOfDate) {

    /**
     * Returns the marked-to-market value of the position, i.e.
     * {@code quantity * lastPrice}.
     */
    public BigDecimal marketValue() {
        return lastPrice.multiply(BigDecimal.valueOf(quantity));
    }

    /**
     * Returns the unrealized change in value against the previous close,
     * i.e. {@code quantity * (lastPrice - previousClose)}.
     */
    public BigDecimal dailyVariation() {
        return lastPrice.subtract(previousClose).multiply(BigDecimal.valueOf(quantity));
    }
}
