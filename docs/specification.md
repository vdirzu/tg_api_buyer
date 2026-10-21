# MASTER PROMPT: Telegram AI API Key Marketplace

## 1. Role and Project Objective

Act as a Senior Python Backend Developer, Telegram Bot Architect, Database Engineer, and UI/UX Designer.

Develop a complete Telegram bot that operates as a marketplace for purchasing AI provider API keys from users.

The bot must support two interface languages:
- Russian
- English

Users select their preferred language during their first interaction with the bot. They then select their preferred account currency:
- USD
- RUB

The core business workflow is:

1. A user opens the bot and completes onboarding.
2. The user opens the product catalog and selects an AI provider.
3. The bot displays the product name, description, purchase rate, and relevant conditions.
4. The user submits an API key for processing.
5. The bot performs a test lookup using a CSV file stored on the server.
6. The bot calculates the purchase amount according to the configured rate and the key's balance recorded in the CSV file.
7. The bot automatically credits the calculated amount to the user's internal balance.
8. The user can request a withdrawal using a bank card or cryptocurrency.
9. The administrator receives the withdrawal request in Telegram and manually processes the payment.

Do not replace the automatic crediting process with mandatory manual approval. Do not introduce additional business rules that contradict these requirements.

## 2. Technology Stack

Use the following technology stack:

- Python 3.12 or another compatible stable Python version.
- aiogram 3 for Telegram Bot API integration.
- PostgreSQL as the primary database.
- SQLAlchemy 2 with asynchronous database access.
- Alembic for database migrations.
- Pydantic Settings for configuration management.
- httpx for external HTTP requests, including exchange-rate retrieval.
- pytest for automated testing.
- Docker and Docker Compose for application and database deployment.
- Redis only if genuinely necessary for distributed state management or other clearly justified functionality.
- CSV files for the initial test database of API keys.

Use asynchronous programming, type hints, structured logging, proper exception handling, and a modular architecture.

Store all secrets and credentials in environment variables. Never hardcode Telegram bot tokens, database passwords, or other secrets.

## 3. First Launch and Onboarding

### Language selection

On the first interaction, display two inline buttons:

- Russian
- English

Save the selected language in the database.

All menus, messages, buttons, validation errors, notifications, and administrative interfaces must support both languages.

### Welcome message

After language selection, display a configurable welcome message and an administrator-uploaded image.

The welcome message must explain the purpose of the marketplace and briefly describe how users can sell supported API keys and receive payment.

Both the Russian and English versions must be editable through the administrator panel.

### Currency selection

After the welcome message, ask the user to select an account currency:

- USD
- RUB

The selected currency determines how the user's balance and financial amounts are displayed.

Users must be able to change their preferred currency later in their profile.

Changing the display currency must not create or destroy value. Convert the displayed balance using the current exchange rate while retaining a consistent underlying accounting record.

Store monetary amounts with appropriate decimal precision. Never use floating-point arithmetic for financial calculations.

## 4. Main Menu and Telegram Interface

Use Telegram Inline Keyboards for the primary navigation. Buttons must appear directly beneath messages rather than in the persistent reply keyboard.

The main menu must contain:

1. Price List
2. Profile
3. Withdraw Funds
4. Support
5. About the Bot

Each main menu screen must support its own configurable image.

The administrator must be able to upload or replace these images through the bot's administrative panel.

Use a consistent, modern interface with concise text, clear navigation, appropriate icons or emojis, and localized button labels.

Implement navigation through inline buttons. Avoid sending unnecessary new messages when an existing menu message can be edited.

Every submenu must provide appropriate Back and Main Menu buttons.

If an image is configured for a menu, display it with the corresponding content. If no image is configured, display the menu without an image.

## 5. Product Catalog and Price List

The Price List menu must display all currently available AI providers as inline buttons.

Each product must have the following configurable properties:

- Unique product ID.
- Product name in Russian.
- Product name in English.
- Description in Russian.
- Description in English.
- Purchase rate per USD of recorded API balance.
- Optional product image.
- Active or inactive status.
- Optional display order.
- Optional explanatory information about eligibility and restrictions.

The administrator must be able to add, edit, deactivate, reactivate, and reorder products through the bot's administrative panel.

The administrator must also be able to change product names, descriptions, purchase rates, and images without modifying source code or restarting the application.

### Product details

When a user selects a product, display:

- Product name.
- Product description.
- Purchase rate per USD of recorded API balance.
- Relevant explanatory information.
- Submit API Key button.
- Back button.

Example:

Product: Example AI Provider

Purchase rate: $0.30 per $1 of recorded balance.

If the submitted key has a recorded balance of $100, the calculated payment is $30 before any applicable regional adjustment.

The example is illustrative. Actual prices must be configured by the administrator.

Only active products may be displayed as available purchase options.

## 6. API Key Submission and Test Verification

### Initial implementation

The first version must use a CSV file stored on the server as its test data source.

The CSV file must contain the records required to simulate API key verification.

Recommended fields:

- `key_fingerprint`
- `provider_id`
- `balance_usd`
- `region_restricted`
- `test_status`

For development testing, the CSV may contain test API-key values. Use synthetic keys rather than real production credentials.

The implementation must support the following workflow:

1. The user selects a provider.
2. The user presses Submit API Key.
3. The bot asks the user to submit the key.
4. The bot looks up the submitted value in the test CSV.
5. The bot verifies that the record belongs to the selected provider.
6. The bot retrieves the configured test balance and regional-restriction flag.
7. The bot displays the verification progress.
8. The bot calculates the payment.
9. The bot automatically credits the user's account balance.
10. The bot displays the result and updated balance.

### Verification progress messages

Display a dynamic verification sequence in the selected language.

Example:

**Step 1: Checking key availability**

Display a loading state while the lookup is processed.

**Step 2: Checking regional restrictions**

Display a loading state and then show the regional status recorded in the CSV.

**Step 3: Checking recorded balance**

Display a loading state while retrieving the test balance.

**Step 4: Calculating purchase value**

Calculate the purchase amount using the product's configured rate and any applicable regional adjustment.

**Step 5: Completing the transaction**

Credit the user's internal balance and display the transaction result.

The progress messages must accurately reflect what the test implementation actually does. Do not claim that a real API provider was contacted or that live permissions, service availability, or regional restrictions were verified when the application only consulted a CSV file.

The interface may simulate the visual progression of verification, but the final result must be determined by the CSV record.

### CSV lookup behavior

If the submitted key is not found:

- Display a localized message explaining that the key could not be verified in the test database.
- Do not credit the user's balance.
- Allow the user to retry or return to the catalog.

If the key belongs to a different provider than the selected product:

- Reject the submission.
- Do not credit the user's balance.
- Display an appropriate localized error.

If the record is marked invalid or otherwise ineligible according to the configured test rules, reject it without crediting funds.

If the CSV file cannot be read or contains invalid data, handle the error gracefully and log the problem. Never treat a database or file-reading failure as a successful verification.

### Key acceptance and duplicate prevention

A successful verification must automatically create a transaction and credit the user's balance.

The same API key must not be accepted repeatedly to generate duplicate payments.

Implement duplicate detection using a stable cryptographic fingerprint, such as HMAC-SHA-256 with a server-side secret.

Store the fingerprint rather than retaining the plaintext key in the transaction history.

The key verification result, duplicate check, transaction creation, and balance update must be implemented safely. Use database transactions and appropriate uniqueness constraints to prevent duplicate crediting under concurrent requests.

If the same key is submitted again, display a localized message explaining that it has already been processed.

Do not add mandatory manual approval to this process.

### Regional restriction rule

The first successfully accepted key submitted by a user must not receive a regional discount solely because it is the first key.

For the second key submitted by the user, the test verification result must indicate that regional restrictions are present.

For the initial test version, implement this deterministic rule:

- First successfully accepted key: no regional restriction is automatically introduced by the test sequence.
- Second successfully accepted key: regional restriction is automatically indicated.
- Only the second key receives the 20% reduction specified below.
- The third and subsequent keys do not receive an automatic regional restriction or discount from this rule.

The CSV lookup must still determine whether a key exists, belongs to the selected provider, and has a recorded balance.

The second-key restriction rule is a test behavior. It must not be represented as a real verification of the provider's regional policies.

Track successful key acceptances per user. Failed submissions and invalid records must not count as accepted keys.

Apply the test rule consistently even if the user switches languages, changes their account currency, or navigates between menus.

The restriction status and adjustment must be visible in the verification result.

## 7. Purchase Calculation and Automatic Balance Credit

The administrator sets the purchase rate for each provider in USD per $1 of recorded API balance.

Let:

- `B` = the USD balance recorded in the CSV.
- `R` = the administrator-configured purchase rate.
- `D` = the regional discount rate, either `0` or `0.20`.

Calculate the payment as:

`payment_usd = B × R × (1 - D)`

Example without a regional discount:

- Recorded balance: $100.
- Purchase rate: 0.30.
- Discount: 0%.
- Payment: $100 × 0.30 = $30.

Example with the regional discount:

- Recorded balance: $100.
- Purchase rate: 0.30.
- Discount: 20%.
- Payment: $100 × 0.30 × 0.80 = $24.

Only the second successfully accepted key receives the 20% discount under the initial test rule.

The administrator must be able to change the purchase rate for each provider through the admin panel.

### Account currency

The purchase rate and calculation must be denominated in USD.

If the user's account currency is USD, credit the calculated USD amount.

If the user's account currency is RUB, convert the calculated amount to RUB using the current USD/RUB exchange rate.

Use a configurable, reputable exchange-rate source. Cache rates for a limited period and handle API failures gracefully.

If a current rate cannot be obtained, do not silently invent a rate. Preserve the pending calculation and inform the user that the conversion is temporarily unavailable.

Record the exchange rate used for each transaction so that historical transactions remain auditable.

### Transaction integrity

On successful acceptance:

1. Create a transaction record.
2. Calculate the purchase amount.
3. Apply the appropriate currency conversion if needed.
4. Credit the user's balance.
5. Record the accepted key fingerprint and verification result.
6. Record the provider, original CSV balance, purchase rate, discount, exchange rate, credited amount, and timestamp.
7. Display the successful result to the user.

The balance update and transaction record must be atomic.

A repeated callback, retry, or simultaneous request must never credit the same key twice.

Display the updated account balance after successful processing.

## 8. User Profile

The Profile menu must display:

- Telegram user ID.
- Registration date.
- Preferred language.
- Account currency.
- Current available balance.
- Total amount earned from accepted keys.
- Total number of accepted keys.
- Total amount withdrawn.
- Number of pending withdrawal requests.

Provide the following profile actions:

- Change Language.
- Change Currency.
- Transaction History.
- Accepted Keys History.
- Withdrawal History.
- Withdraw Funds.
- Contact Support.
- Back to Main Menu.

### Transaction history

Display a paginated history of accepted keys and credits.

For each transaction, show:

- Date and time.
- Provider.
- Transaction status.
- Recorded balance in USD.
- Purchase rate.
- Regional adjustment, if applicable.
- Credited amount and currency.

Do not display plaintext API keys.

### Accepted keys history

Display the provider, acceptance date, transaction amount, and processing result for each accepted key.

Include the regional status and applied discount where relevant.

### Withdrawal history

Display each withdrawal request, requested amount, currency, payment method, creation date, and current status.

Provide clear status labels in Russian and English.

## 9. Withdrawal System

The user must be able to request a withdrawal from their available balance.

Before creating a request, check the configured minimum withdrawal amount for the user's selected currency.

The administrator must be able to configure the minimum withdrawal amount separately for USD and RUB.

The available withdrawal methods are:

1. Bank card.
2. Cryptocurrency.

### Withdrawal amount

Ask the user to enter the desired withdrawal amount.

Validate that:

- The amount is numeric and positive.
- The amount meets the minimum withdrawal threshold.
- The requested amount does not exceed the available balance.
- The amount uses the correct currency precision.

If the user enters an invalid amount, explain the problem and allow them to retry.

### Balance reservation

When a valid withdrawal request is submitted, reserve the requested amount so that the same funds cannot be withdrawn twice.

Track available and reserved funds separately, or implement an equivalent ledger-based accounting model.

If the request is rejected or cancelled, release the reserved amount.

If the request is completed, finalize the deduction.

The user must never be able to create multiple pending requests that collectively exceed their available balance.

### Bank card withdrawal

Offer three card types:

- Visa.
- Mastercard.
- Mir.

After the user selects a card type, ask them to enter the card number in a Telegram message.

Validate the input format sufficiently to detect obvious mistakes, but do not claim that the bank account has been verified.

After receiving the required information, create a withdrawal request and notify the administrator.

The request must contain:

- Withdrawal request ID.
- User ID.
- Requested amount and currency.
- Selected card type.
- Submitted card details.
- Creation timestamp.
- Current status.

The administrator processes the payment manually.

### Cryptocurrency withdrawal

Offer a configurable list of popular cryptocurrency networks and assets.

Initially include:

- USDT on TRON (TRC20).
- USDT on Ethereum (ERC20).
- USDT on BNB Smart Chain (BEP20).
- USDC on Ethereum.
- USDC on Solana.
- TON on The Open Network.

Allow the administrator to add, disable, or modify supported networks and assets through the admin panel.

Clearly distinguish assets and networks. For example, USDT on TRON is not interchangeable with USDT on Ethereum.

The user selects an available asset and network, then enters a destination wallet address.

Validate the address format when practical, but do not claim that the wallet belongs to the user or that a transfer has been completed.

Create a withdrawal request containing:

- Withdrawal request ID.
- User ID.
- Amount and currency.
- Selected asset.
- Selected network.
- Destination wallet address.
- Creation timestamp.
- Current status.

Notify the administrator so that the payment can be processed manually.

### Withdrawal request notifications

Send the administrator an inline message containing the request summary and appropriate actions:

- Mark as Processing.
- Mark as Paid.
- Reject Request.
- Return Funds, when appropriate.
- View User.

Every action must be authorized against the configured administrator list.

When a request is marked as paid, finalize the reserved balance deduction.

When a request is rejected, release the reserved balance and notify the user.

Prevent repeated button presses from processing the same request multiple times.

Record the administrator ID, action, timestamp, and status transition in an audit log.

## 10. About the Bot

The About the Bot menu must contain:

- A configurable description of the service.
- Terms of Service.
- Privacy Policy.
- Contact Support.
- Back to Main Menu.

The Terms of Service and Privacy Policy must be configurable URLs.

The administrator must be able to change the URLs without modifying source code.

Display the links using inline buttons that open the corresponding pages.

If a URL has not been configured, show an administrator-configurable fallback message rather than an invalid link.

The welcome message, service description, and legal-document links must support Russian and English.

## 11. Support System

The user must be able to contact support through the Support menu.

Support configuration must include a Telegram account or support contact configured by the administrator.

Support functionality should include:

- Displaying the configured contact.
- Providing an option to open the contact in Telegram.
- Optionally forwarding user-submitted support messages to the configured administrator or support account.
- Recording message timestamps and user IDs when forwarding is implemented.

Support messages must not interfere with the user's current API key submission or withdrawal workflow.

## 12. Administrative Panel

The administrator panel must be accessible only to authorized Telegram user IDs.

Initially, one administrator will be configured. However, the application must support adding and removing administrators through the admin panel.

Do not rely on a hidden button or menu location for authorization. Verify administrator permissions on the backend for every administrative action.

### Dashboard

Display the following statistics:

- Total registered users.
- New users over the selected period.
- Active users, where a defined activity period is available.
- Total accepted keys.
- Total value credited to users.
- Total value of pending withdrawals.
- Total completed withdrawals.
- Number of pending withdrawal requests.
- Number of failed verification attempts.
- Accepted keys grouped by provider.
- Transaction totals grouped by currency.
- Recent administrative actions.

Allow filtering by date range where practical.

Clearly distinguish total credited amounts from completed withdrawals and current outstanding balances.

### Product management

Administrators must be able to:

- Add a product.
- Edit product names in both languages.
- Edit product descriptions in both languages.
- Change the USD purchase rate.
- Upload or replace a product image.
- Activate or deactivate a product.
- Change display order.
- View transaction statistics for each provider.

### Content management

Administrators must be able to edit:

- Welcome message in Russian and English.
- Main menu descriptions.
- Product catalog descriptions.
- Profile descriptions.
- Verification messages.
- Withdrawal instructions.
- Support text.
- About the Bot text.
- Terms of Service URL.
- Privacy Policy URL.
- Minimum withdrawal amounts.
- Exchange-rate configuration.
- Main menu image.
- Catalog image.
- Profile image.
- Withdrawal image.
- About the Bot image.

Store Telegram file IDs where appropriate so that uploaded images can be reused.

### Financial settings

Administrators must be able to:

- Configure minimum withdrawal amounts for USD and RUB.
- Configure product purchase rates.
- Configure supported withdrawal assets and networks.
- Review pending withdrawal requests.
- View transaction histories.
- View user balances.
- View reserved balances.
- Inspect the reason for rejected or failed requests.

Manual balance adjustments may be supported, but they must require a reason and generate an immutable audit record.

Do not silently overwrite financial history.

### Administrator management

Provide functionality to:

- Add an administrator by Telegram user ID.
- Remove an administrator.
- List active administrators.
- Prevent removal of the final authorized administrator.
- Record changes in the audit log.

The first administrator should be established through a secure environment variable or initial setup procedure.

## 13. CSV Data Management

Use a dedicated CSV file for the initial test lookup system.

The file path must be configurable through environment variables.

Provide a documented CSV format and a sample file containing synthetic test records.

Example:

```csv
key_fingerprint,provider_id,balance_usd,region_restricted,test_status
sample_fingerprint_001,provider_a,100.00,false,valid
sample_fingerprint_002,provider_a,50.00,true,valid
sample_fingerprint_003,provider_b,0.00,false,invalid
```

The sample fingerprints above are illustrative. The implementation must use the same fingerprinting method for lookup that it uses when processing a submitted key.

The CSV lookup must:

- Match the submitted key securely.
- Confirm the provider association.
- Retrieve the recorded USD balance.
- Read the test status.
- Support the required regional test behavior.
- Reject invalid records.
- Handle missing files and malformed rows gracefully.

Do not use the raw API key as a database identifier or write it to application logs.

If the CSV needs to be edited while the bot is running, use a safe reload strategy so that partially written files are not treated as valid data.

The CSV is the source of test verification data. PostgreSQL remains the source of truth for users, balances, transactions, accepted-key fingerprints, withdrawal requests, configuration, and audit records.

## 14. Database Design

Design normalized PostgreSQL tables with appropriate foreign keys, indexes, uniqueness constraints, and timestamps.

At minimum, implement the following entities:

### Users

- Internal user ID.
- Telegram user ID.
- Preferred language.
- Account currency.
- Registration timestamp.
- Account status.
- Other necessary non-sensitive profile settings.

### Products

- Product ID.
- Localized names.
- Localized descriptions.
- Purchase rate.
- Image reference.
- Active status.
- Display order.
- Creation and update timestamps.

### Accepted Keys

- Transaction ID.
- User ID.
- Product ID.
- Key fingerprint.
- Recorded balance in USD.
- Purchase rate at acceptance.
- Regional discount.
- Exchange rate used.
- Credited amount.
- Credited currency.
- Acceptance timestamp.

Use a uniqueness constraint to prevent the same fingerprint from being credited more than once.

### Transactions

- Transaction ID.
- User ID.
- Transaction type.
- Amount.
- Currency.
- Status.
- Related accepted key or withdrawal request.
- Creation timestamp.
- Additional accounting metadata where required.

### Withdrawal Requests

- Request ID.
- User ID.
- Amount.
- Currency.
- Withdrawal method.
- Payment details or a protected reference to them.
- Status.
- Creation timestamp.
- Processing timestamp.
- Administrator ID.
- Rejection reason, when applicable.

### Administrators

- Telegram user ID.
- Role.
- Creation timestamp.
- Active status.

### Configuration

- Setting key.
- Setting value.
- Language, where relevant.
- Update timestamp.
- Administrator responsible for the change, where applicable.

### Audit Log

- Event ID.
- Actor ID.
- Event type.
- Affected entity.
- Timestamp.
- Relevant metadata.

Add any additional tables needed for ledger-based accounting, withdrawal reservations, exchange-rate snapshots, support messages, and idempotency.

Use database migrations rather than relying on automatic table creation in production.

## 15. Security and Reliability

Implement sensible security practices even in the test version.

Requirements:

- Keep secrets in environment variables.
- Do not log raw API keys.
- Use key fingerprints for duplicate detection.
- Restrict the admin panel to authorized Telegram IDs.
- Validate callback ownership and user permissions.
- Validate user input.
- Use parameterized database operations through SQLAlchemy.
- Prevent duplicate transactions.
- Use atomic financial operations.
- Implement idempotent handlers where appropriate.
- Apply rate limits to repeated submissions.
- Handle Telegram API errors and database failures.
- Avoid exposing stack traces to users.
- Store only the minimum payment information needed for processing.
- Restrict access to sensitive withdrawal details.
- Maintain an audit trail of administrative and financial actions.

The initial implementation is a test marketplace. Do not claim that the CSV verification establishes actual provider authorization, API validity, regional eligibility, or compliance with a provider's terms.

## 16. Project Structure

Organize the project into clear modules. Use a structure similar to:

```text
ai_key_marketplace/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── bot.py
│   ├── database/
│   │   ├── session.py
│   │   ├── models.py
│   │   └── repositories/
│   ├── handlers/
│   │   ├── onboarding.py
│   │   ├── main_menu.py
│   │   ├── catalog.py
│   │   ├── verification.py
│   │   ├── profile.py
│   │   ├── withdrawals.py
│   │   ├── support.py
│   │   └── admin/
│   ├── keyboards/
│   ├── services/
│   │   ├── csv_verification.py
│   │   ├── pricing.py
│   │   ├── exchange_rates.py
│   │   ├── accounting.py
│   │   └── withdrawals.py
│   ├── middlewares/
│   ├── locales/
│   │   ├── ru.json
│   │   └── en.json
│   └── utils/
├── data/
│   └── sample_keys.csv
├── migrations/
├── tests/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── README.md
```

You may adjust the structure if there is a clear technical reason, but preserve separation between Telegram handlers, business logic, persistence, and configuration.

## 17. Testing Requirements

Create automated tests for the core business rules.

At minimum, test:

1. Language selection and persistence.
2. Currency selection and changing currency.
3. Product creation and editing.
4. CSV lookup for valid and invalid keys.
5. Rejection of a key belonging to another provider.
6. Correct payment calculation.
7. Application of the 20% discount to the second accepted key only.
8. No automatic discount on the first, third, or subsequent accepted keys.
9. Failed submissions not counting as accepted keys.
10. Duplicate-key rejection.
11. Automatic balance crediting.
12. Correct currency conversion and exchange-rate snapshots.
13. Atomic transaction creation and balance updates.
14. Minimum withdrawal validation.
15. Withdrawal requests that exceed the available balance.
16. Reservation and release of funds.
17. Correct handling of paid and rejected withdrawals.
18. Administrator authorization.
19. Administrator management.
20. Content and image configuration.
21. Recovery from malformed CSV data.
22. Recovery from exchange-rate API failure.
23. Prevention of duplicate financial operations after retries.

Use test fixtures and synthetic API keys. Do not use real provider credentials.

## 18. Deployment and Documentation

Provide:

- Complete source code.
- A `.env.example` file.
- A sample CSV file.
- Database migration instructions.
- Docker Compose configuration.
- Local development instructions.
- Production deployment instructions.
- Instructions for creating and configuring the Telegram bot through BotFather.
- Instructions for setting the initial administrator.
- Instructions for uploading and editing menu images.
- Instructions for managing products and purchase rates.
- Instructions for editing CSV test records.
- Instructions for configuring exchange-rate retrieval.
- Instructions for managing withdrawal requests.
- Troubleshooting documentation.

The project must start from a clean environment by following the README instructions.

Do not omit essential modules, replace core functions with placeholders, or leave critical business logic as TODO comments.

## 19. Implementation Workflow

Develop the project in the following order:

Phase 1: Project scaffolding, configuration, PostgreSQL, SQLAlchemy models, and migrations.

Phase 2: Localization, onboarding, currency selection, and main navigation.

Phase 3: Product catalog, administrator product management, and image management.

Phase 4: CSV-based verification, duplicate detection, pricing, regional test rules, and automatic balance crediting.

Phase 5: Profile, transaction history, and account currency conversion.

Phase 6: Withdrawal workflows, balance reservations, administrator notifications, and manual payout status management.

Phase 7: Administrative dashboard, statistics, settings, content management, and audit logs.

Phase 8: Automated tests, error handling, Docker configuration, and documentation.

After each phase, verify that the implemented functionality works before continuing.

## 20. Acceptance Criteria

The project is considered complete only when:

- A user can select Russian or English.
- A user can select USD or RUB and change the preference later.
- The catalog displays administrator-managed products.
- Product names, descriptions, prices, and images can be changed through the admin panel.
- Users can submit keys for CSV-based test verification.
- The verification sequence displays the appropriate localized progress messages.
- Successful keys are accepted automatically.
- The first accepted key receives no automatic regional discount.
- The second accepted key receives the 20% regional discount.
- The third and subsequent keys receive no automatic discount from this test rule.
- The payment is calculated from the CSV balance and the administrator-configured USD purchase rate.
- RUB balances use a recorded current exchange rate.
- Successful transactions are credited automatically and cannot be duplicated.
- Users can view their profile, balance, accepted-key history, transaction history, and withdrawal history.
- Users can request withdrawals to Visa, Mastercard, Mir, or supported cryptocurrency networks.
- Withdrawal requests are delivered to authorized administrators.
- Reserved funds are handled correctly.
- Administrators can mark withdrawals as paid or rejected.
- Rejected withdrawals release reserved funds.
- Administrators can manage products, content, images, minimum withdrawal amounts, supported networks, and administrator access.
- Statistics are available in the administrative dashboard.
- Sensitive values are not exposed in application logs.
- Database migrations and automated tests are provided.
- The project can be deployed using the documented instructions.

Prioritize correctness, financial integrity, maintainability, and a clean Telegram user experience.

Begin by presenting a concise implementation plan and the proposed database schema. Then implement the project in working stages, validating each stage before proceeding.