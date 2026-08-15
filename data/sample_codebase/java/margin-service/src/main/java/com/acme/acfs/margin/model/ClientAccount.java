package com.acme.acfs.margin.model;

/**
 * A clearing client account registered in the {@code clients} table.
 *
 * <p>The {@code marginModel} selects how margin is calculated for the
 * account: {@link MarginModel#STANDARD} applies the venue rate to gross
 * notional, while {@link MarginModel#PORTFOLIO} applies a diversification
 * offset. Only {@link Status#ACTIVE} accounts are included in a margin run.
 */
public class ClientAccount {

    /** Lifecycle status of the account. */
    public enum Status {
        ACTIVE,
        SUSPENDED,
        CLOSED
    }

    /** Margining model applied to the account. */
    public enum MarginModel {
        STANDARD,
        PORTFOLIO
    }

    private final String clientId;
    private final String clientName;
    private final Status status;
    private final MarginModel marginModel;

    public ClientAccount(String clientId, String clientName, Status status, MarginModel marginModel) {
        this.clientId = clientId;
        this.clientName = clientName;
        this.status = status;
        this.marginModel = marginModel;
    }

    /** Returns the client identifier, e.g. {@code ACME-101}. */
    public String getClientId() {
        return clientId;
    }

    public String getClientName() {
        return clientName;
    }

    public Status getStatus() {
        return status;
    }

    public MarginModel getMarginModel() {
        return marginModel;
    }

    /** Returns true if the account participates in margin runs. */
    public boolean isActive() {
        return status == Status.ACTIVE;
    }
}
