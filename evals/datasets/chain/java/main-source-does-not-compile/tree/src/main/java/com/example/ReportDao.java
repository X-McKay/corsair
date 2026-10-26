package com.example;

import com.example.legacy.LegacyConnectionPool;
import java.sql.ResultSet;

public class ReportDao {
    private final LegacyConnectionPool pool;

    public ReportDao(LegacyConnectionPool pool) {
        this.pool = pool;
    }

    /** Total for one account. */
    public ResultSet total(String account) throws Exception {
        return pool.borrow().createStatement()
            .executeQuery("SELECT SUM(amount) FROM entries WHERE account = '" + account + "'");
    }
}
