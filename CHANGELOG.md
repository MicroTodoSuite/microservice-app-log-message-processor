## [1.5.1](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.5.0...v1.5.1) (2026-09-14)


### Bug Fixes

* **ci:** repoint to the latest .github reusable workflow refs ([#28](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/28)) ([6fe754d](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/6fe754d48e489fd8e2509210d7766379cd9c0e4a)), closes [#142](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/142) [#19](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/19)

# [1.5.0](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.4.0...v1.5.0) (2026-09-13)


### Features

* **metrics:** record log-message-processor metrics through opentelemetry ([502dce8](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/502dce83007987f15db715cde6e55e79cd6bc4f0))
* **metrics:** record log-message-processor metrics through opentelemetry ([#25](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/25)) ([468017f](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/468017f5de0f2888bf7dc1b694cb21fcfaa97318)), closes [MicroTodoSuite/microservice-app-gitops#136](https://github.com/MicroTodoSuite/microservice-app-gitops/issues/136) [MicroTodoSuite/microservice-app-gitops#136](https://github.com/MicroTodoSuite/microservice-app-gitops/issues/136)

# [1.4.0](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.3.1...v1.4.0) (2026-09-13)


### Features

* **tracing:** trace log-message-processor through opentelemetry ([#23](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/23)) ([1aacb98](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/1aacb982d921e1cbc0f7e87818a4101f286221c1)), closes [MicroTodoSuite/microservice-app-todos-api#22](https://github.com/MicroTodoSuite/microservice-app-todos-api/issues/22) [#123](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/123) [MicroTodoSuite/microservice-app-todos-api#22](https://github.com/MicroTodoSuite/microservice-app-todos-api/issues/22)

## [1.3.1](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.3.0...v1.3.1) (2026-09-09)


### Bug Fixes

* **startup:** resolve runtime definitions before execution ([693a8a5](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/693a8a595f8e03ceb6babf12ec5afdf5a6ac47bc))

# [1.3.0](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.2.1...v1.3.0) (2026-09-09)


### Bug Fixes

* **ci:** target replacement AWS account ([d7c38e8](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/d7c38e822f6017d49a0ad2f81050ac1a8c0c5f35))


### Features

* **us3:** log-message-processor health, correlation, and Redis reconnection ([#13](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/13)) ([cf527ef](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/cf527eff0454351de81e549c5dbea9aba682a273))

## [1.2.1](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.2.0...v1.2.1) (2026-08-24)


### Bug Fixes

* **ci:** publish images to the migrated AWS account ([46c176e](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/46c176e4b2bf5a9032d4ac5a7964e1264865182b))

# [1.2.0](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.1.0...v1.2.0) (2026-08-19)


### Bug Fixes

* upgrade base image os packages to clear trivy high findings (util-linux cve-2026-53615) ([#8](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/issues/8)) ([501d4e4](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/501d4e4e73ce0552322fb030c87285526d955c2d))


### Features

* initialize project specification and architecture constitution ([5d50871](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/5d50871d3b8f1d9f08c19e7f5869f6260c75c4f6))

# [1.1.0](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/compare/v1.0.0...v1.1.0) (2025-04-25)


### Features

* **pipeline:** add update of pipeline ([c37fbc6](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/c37fbc664286e23e4b539a2d31b4e61d0ddd5498))

# 1.0.0 (2025-04-25)


### Bug Fixes

* **pipeline:** update pipeline ([e2a7ea3](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/e2a7ea3453f964c30c07ff866a28332445c6ba82))


### Features

* add microservice for log message processor ([91ef589](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/91ef589585242afcb0780a97ac060aaf66f9fc77))
* add release workflow ([4df4be4](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/4df4be409af12199726c43cd8d025e68af225ffe))
* **pipeline:** add pipeline of development ([04ae555](https://github.com/MicroTodoSuite/microservice-app-log-message-processor/commit/04ae5554c726611ff4c992f85e367ba30b9d26cd))
