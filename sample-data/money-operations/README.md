# Mandate Money Operations synthetic dataset

This package models a synthetic $47.5 million annualized technology retailer across six monthly periods. It is designed for an evidence-backed financial variance agent. All names, transactions, amounts, invoices, and context are fictional.

## Focus comparison

February 2026 versus January 2026. Gross revenue rises 18.0%. Enterprise revenue rises 32.0%. Northstar Commerce, Atlas Industrial, and Forma Retail Group contribute exactly 64.0% of the total revenue increase. Expense drivers include a NovaERP annual renewal, greater logistics volume and expedited shipping, and performance bonuses with no headcount change. SmartHub Pro drives 87.5% of the increase in refunds. A $57,000 Other Opex increase reconciles to an unmapped clearing batch but deliberately remains causally unexplained.

## Files

- Mandate_Money_Operations_Dataset.xlsx: formula-driven review workbook
- monthly_account_summaries.csv: monthly GL-style summaries
- revenue_transactions.csv: signed sales and refund transactions
- expense_transactions.csv: expense transactions with driver categories
- customer, product, channel, region, and vendor dimensions
- business_context_history.json: auditable context retained across close runs
- expected_driver_answers.json: expected evidence-backed outputs
- data_dictionary.csv: field definitions
- validation_manifest.json: exact expected checks and SHA-256 hashes

The context ledger may explain a computed variance, but it cannot replace source transactions or change calculated amounts.
