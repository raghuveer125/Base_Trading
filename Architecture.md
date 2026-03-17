# Item 1 — Repo structure and standards

## Checklist
- [x] Create folder structure
- [x] Add root files
- [x] Add shared config loader
- [x] Add shared logger
- [x] Add health model
- [x] Add stub entrypoints for all services
- [x] Add per-service README files
- [x] Add config YAML placeholders
- [x] Add bootstrap and local run scripts
- [x] Verify local imports work
- [x] Verify at least 2 services start successfully
- [x] Verify docker compose file is valid

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test placeholder added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 2 — Service skeleton and shared contracts

## Checklist
- [x] Define internal event naming
- [x] Define message envelope
- [x] Define symbol format standard
- [x] Define timeframe format standard
- [x] Define timestamp standard
- [x] Define schema versioning standard
- [x] Define error event schema
- [x] Define health event schema
- [x] Define market data event schemas
- [x] Define bar event schema
- [x] Define indicator event schema
- [x] Define order command/update schemas
- [x] Verify model creation tests
- [x] Verify imports pass
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated


----->

# Item 3 — Auth service production skeleton

## Checklist
- [x] Add auth-specific settings
- [x] Add auth session model
- [x] Add auth status model
- [x] Add local session persistence
- [x] Add FYERS auth provider stub
- [x] Add auth bootstrap workflow
- [x] Add auth validation workflow
- [x] Add auth startup logging
- [x] Add auth unit tests
- [x] Verify auth tests pass
- [x] Verify auth service starts with valid token
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 4 — Auth API and health endpoint

## Checklist
- [x] Add FastAPI auth application
- [x] Add health endpoint
- [x] Add auth status endpoint
- [x] Add auth bootstrap endpoint
- [x] Add API mode for auth service
- [x] Add auth API tests
- [x] Verify API tests pass
- [x] Verify auth API starts
- [x] Verify endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 5 — Market data gateway production skeleton

## Checklist
- [x] Add market data gateway settings
- [x] Add raw market packet model
- [x] Add gateway status model
- [x] Add market data normalizer
- [x] Add stub publisher
- [x] Add stub price feed
- [x] Add gateway service
- [x] Add gateway API
- [x] Add gateway main entrypoint
- [x] Add gateway unit tests
- [x] Add gateway API tests
- [x] Verify tests pass
- [x] Verify stub mode runs
- [x] Verify API mode runs
- [x] Verify gateway endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 7 — Kafka topic admin and real publish mode

## Checklist
- [x] Add Kafka topic admin module
- [x] Add topic ensure flow
- [x] Add Kafka producer ack logging
- [x] Integrate topic ensure into stub mode
- [x] Integrate topic ensure into API mode
- [x] Enable real Kafka mode through env
- [x] Add Kafka admin tests
- [x] Verify tests pass
- [x] Verify topic creation path works
- [x] Verify real Kafka publish works
- [x] Verify gateway endpoints still work
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 8 — Kafka consumer skeleton for bar builder

## Checklist
- [x] Add Kafka consumer module
- [x] Add bar builder status model
- [x] Add tick-to-bar processor stub
- [x] Add bar publisher
- [x] Add bar builder service
- [x] Add bar builder API
- [x] Add bar builder main entrypoint
- [x] Add Kafka consumer tests
- [x] Add bar builder unit tests
- [x] Add bar builder API tests
- [x] Verify tests pass
- [x] Verify bar builder stub mode runs
- [x] Verify bar builder API mode runs
- [x] Verify bar builder endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 9 — Stateful 1-minute candle aggregation

## Checklist
- [x] Add in-memory bar state store
- [x] Add bar key generation
- [x] Add bar window calculation
- [x] Add create-bar path from first tick
- [x] Add update-bar path from subsequent ticks
- [x] Add stateful aggregation into bar builder service
- [x] Expose open bar count in status
- [x] Update bar builder tests for aggregation
- [x] Update bar builder API tests
- [x] Verify tests pass
- [x] Verify stateful aggregation works
- [x] Verify bar builder endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 10 — Finalized bar close and closed-bar publishing flow

## Checklist
- [x] Add closed-bar Kafka topic setting
- [x] Add close-on-next-minute control
- [x] Add closed-bar publish path
- [x] Add state store pop support
- [x] Add completed bar close logic
- [x] Add closed bar count in status
- [x] Add tests for close-and-publish flow
- [x] Update API tests
- [x] Verify tests pass
- [x] Verify close flow works in stub mode
- [x] Verify endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 11 — Redis hot-state integration skeleton

## Checklist
- [x] Add Redis settings
- [x] Add Redis client module
- [x] Add Redis cache writer for bar builder
- [x] Cache open bars to Redis
- [x] Cache closed bars to Redis
- [x] Cache bar builder status to Redis
- [x] Integrate Redis into bar builder stub mode
- [x] Integrate Redis into bar builder API mode
- [x] Add Redis unit tests
- [x] Add cache writer tests
- [x] Verify tests pass
- [x] Verify bar builder runs with Redis enabled
- [x] Verify API mode runs with Redis enabled
- [x] Verify Redis keys are written
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 12 — Redis hot-state integration for market data gateway

## Checklist
- [x] Add market data gateway cache writer
- [x] Cache latest tick to Redis
- [x] Cache market data gateway status to Redis
- [x] Integrate Redis into market data gateway stub mode
- [x] Integrate Redis into market data gateway API mode
- [x] Add market data gateway cache writer tests
- [x] Update market data gateway tests
- [x] Verify tests pass
- [x] Verify gateway runs with Redis enabled
- [x] Verify API mode runs with Redis enabled
- [x] Verify Redis keys are written
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 13 — PostgreSQL persistence skeleton for closed bars

## Checklist
- [x] Add PostgreSQL settings
- [x] Add PostgreSQL client module
- [x] Add closed bar repository
- [x] Create closed bars table on startup
- [x] Persist closed bars to PostgreSQL
- [x] Integrate PostgreSQL into bar builder stub mode
- [x] Integrate PostgreSQL into bar builder API mode
- [x] Add PostgreSQL unit tests
- [x] Add repository tests
- [x] Update bar builder tests
- [x] Verify tests pass
- [x] Verify bar builder runs with PostgreSQL enabled
- [x] Verify closed bar table is created
- [x] Verify closed bars can be inserted
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 14 — Database upsert and dedupe for closed bars

## Checklist
- [x] Add unique key for closed bars
- [x] Add upsert flow for closed bars
- [x] Replace insert-only persistence with upsert persistence
- [x] Update repository tests
- [x] Update bar builder service integration
- [x] Verify tests pass
- [x] Verify table has unique constraint
- [x] Verify count query still works
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 15 — Migration from stub bars to replayable closed-bar flow

## Checklist
- [x] Add replay status model
- [x] Add repository fetch method for closed bars
- [x] Add closed-bar replay service
- [x] Add replay API endpoints
- [x] Include replay routes in bar builder API
- [x] Add replay service tests
- [x] Add replay API tests
- [x] Verify tests pass
- [x] Verify replay endpoints respond successfully
- [x] Verify closed bars can be loaded from DB
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 16 — Indicator engine skeleton consuming closed bars

## Checklist
- [x] Add indicator engine settings
- [x] Add indicator engine status model
- [x] Add closed-bar to indicator processor
- [x] Add indicator publisher
- [x] Add indicator engine service
- [x] Add indicator engine API
- [x] Add indicator engine main entrypoint
- [x] Add indicator engine unit tests
- [x] Add indicator engine API tests
- [x] Verify tests pass
- [x] Verify indicator engine stub mode runs
- [x] Verify indicator engine API mode runs
- [x] Verify indicator engine endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 17 — Redis hot-state integration for indicator engine

## Checklist
- [x] Add indicator cache writer
- [x] Cache latest indicator to Redis
- [x] Cache indicator engine status to Redis
- [x] Integrate Redis into indicator engine stub mode
- [x] Integrate Redis into indicator engine API mode
- [x] Add indicator cache writer tests
- [x] Update indicator engine tests
- [x] Verify tests pass
- [x] Verify indicator engine runs with Redis enabled
- [x] Verify API mode runs with Redis enabled
- [x] Verify Redis keys are written
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 18 — PostgreSQL persistence skeleton for indicators

## Checklist
- [x] Add indicator repository
- [x] Create indicators table on startup
- [x] Persist indicators to PostgreSQL
- [x] Integrate PostgreSQL into indicator engine stub mode
- [x] Integrate PostgreSQL into indicator engine API mode
- [x] Add indicator repository tests
- [x] Update indicator engine tests
- [x] Verify tests pass
- [x] Verify indicator engine runs with PostgreSQL enabled
- [x] Verify indicators table is created
- [x] Verify indicator count query works
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 19 — Indicator replay API from PostgreSQL

## Checklist
- [x] Add indicator replay status model
- [x] Add repository fetch method for indicators
- [x] Add indicator replay service
- [x] Add replay API endpoints
- [x] Include replay routes in indicator engine API
- [x] Add replay service tests
- [x] Add replay API tests
- [x] Verify tests pass
- [x] Verify replay endpoints respond successfully
- [x] Verify indicators can be loaded from DB
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 20 — Strategy runtime skeleton reading indicator replay data

## Checklist
- [x] Add strategy runtime settings
- [x] Add strategy runtime status model
- [x] Add indicator replay reader for strategy runtime
- [x] Add strategy processor
- [x] Add strategy runtime service
- [x] Add strategy runtime API
- [x] Add strategy runtime main entrypoint
- [x] Add strategy runtime unit tests
- [x] Add strategy runtime API tests
- [x] Verify tests pass
- [x] Verify strategy runtime stub mode runs
- [x] Verify strategy runtime API mode runs
- [x] Verify strategy runtime endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 21 — Risk service skeleton reading strategy signals

## Checklist
- [x] Add risk service settings
- [x] Add risk service status model
- [x] Add strategy signal reader
- [x] Add risk processor
- [x] Add risk service
- [x] Add risk service API
- [x] Add risk service main entrypoint
- [x] Add risk service unit tests
- [x] Add risk service API tests
- [x] Verify tests pass
- [x] Verify risk service stub mode runs
- [x] Verify risk service API mode runs
- [x] Verify risk service endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 22 — Execution service skeleton reading approved risk output

## Checklist
- [x] Add execution service settings
- [x] Add execution service status model
- [x] Add approved signal reader
- [x] Add execution processor
- [x] Add execution service
- [x] Add execution service API
- [x] Add execution service main entrypoint
- [x] Add execution service unit tests
- [x] Add execution service API tests
- [x] Verify tests pass
- [x] Verify execution service stub mode runs
- [x] Verify execution service API mode runs
- [x] Verify execution service endpoints respond successfully
- [x] Docs updated

## Definition of done
- [x] Code written
- [x] Config added
- [x] Logs added
- [x] Test added
- [x] Local run successful
- [x] Failure case checked
- [x] Output verified
- [x] Docs updated

# Item 23 — Broker adapter skeleton for FYERS
## Checklist

  * Add broker adapter interface
  * Add FYERS broker adapter skeleton
  * Add broker factory
  * Add broker health model
  * Add place-order request/response models
  * Add broker health endpoint
  * Add stub and live broker modes
  * Add execution service broker wiring
  * Add broker adapter unit tests
  * Add broker API tests
  * Verify tests pass
  * Verify stub broker accepts test order
  * Verify live broker returns skeleton response
  * Docs updated

## Definition of done

  * Code written
  * Config reused
  * Logs added
  * Test added
  * Local run successful
  * Failure case checked
  * Output verified
  * Docs updated

# Item 24 — Order command to broker order placement
## Checklist

  * Add broker request validation
  * Add idempotency key generation
  * Add correlation id on order submission
  * Add FYERS payload mapping
  * Add stub broker submission payload echo
  * Add live FYERS place-order call
  * Add response normalization
  * Add live submission error handling
  * Add processor tests for idempotency
  * Add broker request validation tests
  * Add API test coverage for broker response fields
  * Verify tests pass
  * Verify stub path returns accepted with idempotency key
  * Verify live path returns accepted or controlled error
  * Docs updated

## Definition of done

  * Code written
  * Request validation added
  * Idempotency added
  * Logs added
  * Test added
  * Stub mode verified
  * Live mode path implemented
  * Failure case checked
  * Output verified
  * Docs updated

# Item 25 — Order state machine and lifecycle tracking
## Checklist

  * Add internal order status enum
  * Add allowed transition rules
  * Add invalid transition guard
  * Add broker status normalization
  * Add lifecycle event model
  * Add in-memory lifecycle store
  * Track submitted to acknowledged flow
  * Add broker update application flow
  * Add order listing endpoint
  * Add order history endpoint
  * Add broker update simulation endpoint
  * Add state machine unit tests
  * Add lifecycle service tests
  * Add API tests for lifecycle endpoints
  * Verify tests pass
  * Verify stub order moves through lifecycle
  * Docs updated

## Definition of done

  * Code written
  * State machine added
  * Transition guards added
  * Broker normalization added
  * Logs preserved
  * Tests added
  * Stub lifecycle verified
  * Failure case checked
  * Output verified
  * Docs updated

