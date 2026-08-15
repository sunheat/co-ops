package com.acme.acfs.margin.model;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * A single executed trade imported from a nightly venue file.
 *
 * <p>Trade records originate from the Python-based Trade Importer, which
 * parses venue files, validates them, and loads accepted records into the
 * {@code trades} table. The margin service consumes trades only as reference
 * data: position records (see {@link Position}) drive the margin calculation.
 *
 * <p>Rejects during import are written to a reject report and block the
 * downstream margin run, which is a common support-investigation scenario.
 */
public record Trade(
        String tradeId,
        String clientId,
        Venue venue,
        String instrument,
        long quantity,
        BigDecimal price,
        LocalDate tradeDate,
        String importBatch) {

    /**
     * Returns the notional value of the trade, i.e. {@code quantity * price}.
     */
    public BigDecimal notional() {
        return price.multiply(BigDecimal.valueOf(quantity));
    }
}
