package com.acme.acfs.margin.model;

/**
 * Currencies used across the ACFS clearing platform.
 *
 * <p>Each venue settles in its own base currency, and client margin results
 * are stored in the venue currency in the {@code margin_results} table.
 */
public enum Currency {
    SGD,
    AUD,
    HKD,
    USD
}
