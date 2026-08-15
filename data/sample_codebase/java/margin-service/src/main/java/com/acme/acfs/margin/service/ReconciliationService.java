package com.acme.acfs.margin.service;

import com.acme.acfs.margin.model.Position;
import com.acme.acfs.margin.model.Venue;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/**
 * Aggregates client-level positions and compares them with the aggregate
 * positions published by the venue.
 *
 * <p>This is the ACFS Position Reconciler. It runs after the margin run in
 * the nightly batch window and raises a {@link ReconciliationBreak} for every
 * instrument where the ACFS aggregate does not match the venue figure.
 * Breaks must be triaged before morning reporting; a frequent root cause is a
 * manual position adjustment that was not reflected in the venue submission.
 */
public class ReconciliationService {

    /**
     * A single reconciliation break for one instrument.
     *
     * @param instrument   instrument the break was raised for
     * @param acfsQuantity aggregate quantity reconstructed from client positions
     * @param venueQuantity aggregate quantity published by the venue
     */
    public record ReconciliationBreak(String instrument, long acfsQuantity, long venueQuantity) {

        /** Returns the signed difference {@code acfsQuantity - venueQuantity}. */
        public long difference() {
            return acfsQuantity - venueQuantity;
        }
    }

    /**
     * Reconciles client positions against venue aggregate positions.
     *
     * <p>Client positions of other venues are ignored. Instruments present on
     * only one side are compared against zero on the missing side, so both
     * orphan positions and missing venue lines surface as breaks.
     *
     * @param venue           venue being reconciled
     * @param asOfDate        business date of the position snapshot
     * @param clientPositions client-level positions held by ACFS
     * @param venueAggregates venue-published aggregate quantity per instrument
     * @return all breaks found, sorted by instrument; empty if fully matched
     */
    public List<ReconciliationBreak> reconcile(Venue venue, LocalDate asOfDate,
                                               List<Position> clientPositions,
                                               Map<String, Long> venueAggregates) {
        Map<String, Long> acfsAggregates = aggregateByInstrument(clientPositions, venue, asOfDate);

        TreeSet<String> instruments = new TreeSet<>();
        instruments.addAll(acfsAggregates.keySet());
        instruments.addAll(venueAggregates.keySet());

        List<ReconciliationBreak> breaks = new ArrayList<>();
        for (String instrument : instruments) {
            long acfsQuantity = acfsAggregates.getOrDefault(instrument, 0L);
            long venueQuantity = venueAggregates.getOrDefault(instrument, 0L);
            if (acfsQuantity != venueQuantity) {
                breaks.add(new ReconciliationBreak(instrument, acfsQuantity, venueQuantity));
            }
        }
        return breaks;
    }

    /** Sums client position quantities per instrument for the given venue and date. */
    private Map<String, Long> aggregateByInstrument(List<Position> clientPositions,
                                                    Venue venue, LocalDate asOfDate) {
        Map<String, Long> aggregates = new LinkedHashMap<>();
        for (Position position : clientPositions) {
            if (position.venue() != venue || !position.asOfDate().equals(asOfDate)) {
                continue;
            }
            aggregates.merge(position.instrument(), position.quantity(), Long::sum);
        }
        return aggregates;
    }
}
