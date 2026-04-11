migrations = {
    "1.0.0": [
        """CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'invoice',
            contact_id INTEGER,
            date TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'draft',
            subtotal REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0,
            total REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            transaction_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id)
        )""",
        """CREATE TABLE invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )""",
    ],
}
