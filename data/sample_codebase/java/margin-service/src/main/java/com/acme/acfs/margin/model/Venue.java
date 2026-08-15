package com.acme.acfs.margin.model;

/**
 * Trading venues supported by ACFS.
 *
 * <p>Venue identifiers follow the naming convention used across the corpus
 * (fictional usage only). Each venue defines the base currency in which its
 * margin runs are calculated and reported.
 */
public enum Venue {
    SGX(Currency.SGD),
    ASX(Currency.AUD),
    HKEX(Currency.HKD);

    private final Currency baseCurrency;

    Venue(Currency baseCurrency) {
        this.baseCurrency = baseCurrency;
    }

    /** Returns the settlement currency used for margin results at this venue. */
    public Currency baseCurrency() {
        return baseCurrency;
    }
}
