package com.acme.acfs.margin.service;

import com.acme.acfs.margin.model.ClientAccount;
import com.acme.acfs.margin.model.MarginReport;
import com.acme.acfs.margin.model.Position;
import com.acme.acfs.margin.model.Venue;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Calculates initial and variation margin per client account for a venue.
 *
 * <p>This is the core calculation of the ACFS Margin Service. For each daily
 * run it produces a {@link MarginReport} whose per-client figures are written
 * to the {@code margin_results} table. Downstream consumers include the
 * Invoice Generator (fee and margin-call invoicing) and risk &amp; compliance
 * reporting.
 *
 * <h2>Margin model (simplified)</h2>
 * <ul>
 *   <li><b>Initial margin</b>: venue rate applied to the gross notional of
 *       the client's positions, i.e.
 *       {@code sum(|quantity| * lastPrice) * venueRate}. Portfolio accounts
 *       receive a diversification offset via {@link #PORTFOLIO_FACTOR}.</li>
 *   <li><b>Variation margin</b>: daily mark-to-market change, i.e.
 *       {@code sum(quantity * (lastPrice - previousClose))}.</li>
 * </ul>
 *
 * <p>Amounts are rounded to two decimals in the venue's base currency.
 */
public class MarginCalculator {

    private static final DateTimeFormatter RUN_ID_DATE = DateTimeFormatter.ofPattern("yyyyMMdd");

    /** Venue-specific initial margin rates applied to gross notional. */
    private static final Map<Venue, BigDecimal> INITIAL_MARGIN_RATES = Map.of(
            Venue.SGX, new BigDecimal("0.08"),
            Venue.ASX, new BigDecimal("0.10"),
            Venue.HKEX, new BigDecimal("0.09"));

    /** Diversification offset applied to portfolio-margin accounts. */
    private static final BigDecimal PORTFOLIO_FACTOR = new BigDecimal("0.90");

    private static final int AMOUNT_SCALE = 2;

    /**
     * Runs the daily margin calculation for a single venue.
     *
     * <p>Only active client accounts are included. Positions belonging to
     * other venues or to clients without an account record are ignored; the
     * reconciliation step is responsible for surfacing such anomalies.
     *
     * @param runDate   business date of the margin run
     * @param venue     venue the run is calculated for
     * @param accounts  client accounts registered in the {@code clients} table
     * @param positions client-level positions as of {@code runDate}
     * @return the margin report for the run
     */
    public MarginReport runMargin(LocalDate runDate, Venue venue,
                                  List<ClientAccount> accounts, List<Position> positions) {
        Map<String, List<Position>> positionsByClient = groupByClient(positions, venue);

        List<MarginReport.ClientMarginResult> results = new ArrayList<>();
        for (ClientAccount account : accounts) {
            if (!account.isActive()) {
                continue;
            }
            List<Position> clientPositions =
                    positionsByClient.getOrDefault(account.getClientId(), List.of());
            BigDecimal initialMargin = calculateInitialMargin(clientPositions, venue, account);
            BigDecimal variationMargin = calculateVariationMargin(clientPositions);
            results.add(new MarginReport.ClientMarginResult(
                    account.getClientId(), initialMargin, variationMargin));
        }

        String runId = buildRunId(runDate, venue);
        return new MarginReport(runId, runDate, venue, List.copyOf(results));
    }

    /**
     * Calculates initial margin for one client as the venue rate applied to
     * gross notional, with a diversification offset for portfolio accounts.
     */
    private BigDecimal calculateInitialMargin(List<Position> clientPositions,
                                              Venue venue, ClientAccount account) {
        BigDecimal grossNotional = BigDecimal.ZERO;
        for (Position position : clientPositions) {
            grossNotional = grossNotional.add(
                    position.lastPrice().multiply(BigDecimal.valueOf(Math.abs(position.quantity()))));
        }
        BigDecimal rate = INITIAL_MARGIN_RATES.get(venue);
        BigDecimal margin = grossNotional.multiply(rate);
        if (account.getMarginModel() == ClientAccount.MarginModel.PORTFOLIO) {
            margin = margin.multiply(PORTFOLIO_FACTOR);
        }
        return margin.setScale(AMOUNT_SCALE, RoundingMode.HALF_UP);
    }

    /**
     * Calculates variation margin for one client as the daily mark-to-market
     * change across all of the client's positions.
     */
    private BigDecimal calculateVariationMargin(List<Position> clientPositions) {
        BigDecimal variation = BigDecimal.ZERO;
        for (Position position : clientPositions) {
            variation = variation.add(position.dailyVariation());
        }
        return variation.setScale(AMOUNT_SCALE, RoundingMode.HALF_UP);
    }

    /** Groups the positions of the given venue by client identifier. */
    private Map<String, List<Position>> groupByClient(List<Position> positions, Venue venue) {
        Map<String, List<Position>> grouped = new LinkedHashMap<>();
        for (Position position : positions) {
            if (position.venue() != venue) {
                continue;
            }
            grouped.computeIfAbsent(position.clientId(), key -> new ArrayList<>()).add(position);
        }
        return grouped;
    }

    /** Builds a run identifier such as {@code MR-20240315-SGX}. */
    private String buildRunId(LocalDate runDate, Venue venue) {
        return String.format("MR-%s-%s", RUN_ID_DATE.format(runDate), venue.name());
    }
}
