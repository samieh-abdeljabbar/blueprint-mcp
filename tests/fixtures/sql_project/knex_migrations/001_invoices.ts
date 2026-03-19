import { Knex } from "knex";

export async function up(knex: Knex): Promise<void> {
    await knex.schema.createTable("invoices", (table) => {
        table.increments("id").primary();
        table.string("invoice_number").notNullable();
        table.decimal("amount", 10, 2);
        table.integer("customer_id").unsigned().references("id").inTable("customers");
    });
}

export async function down(knex: Knex): Promise<void> {
    await knex.schema.dropTable("invoices");
}
