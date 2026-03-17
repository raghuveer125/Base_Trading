from __future__ import annotations

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class KafkaTopicAdmin:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("shared.kafka.admin")
        self._admin: KafkaAdminClient | None = None

    def connect(self) -> None:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "kafka_admin_skipped",
                reason="kafka_disabled",
            )
            return

        self._admin = KafkaAdminClient(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=f"{self._settings.kafka_client_id}-admin",
        )

        self._logger.info(
            "kafka_admin_connected",
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
        )

    def ensure_topic(self, topic_name: str) -> None:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "topic_ensure_skipped",
                reason="kafka_disabled",
                topic=topic_name,
            )
            return

        if not self._settings.kafka_auto_create_topics:
            self._logger.info(
                "topic_ensure_skipped",
                reason="auto_create_disabled",
                topic=topic_name,
            )
            return

        if self._admin is None:
            raise RuntimeError("Kafka admin client is not connected")

        topic = NewTopic(
            name=topic_name,
            num_partitions=self._settings.kafka_topic_partitions,
            replication_factor=self._settings.kafka_topic_replication_factor,
        )

        try:
            self._admin.create_topics([topic], validate_only=False)
            self._logger.info(
                "topic_created",
                topic=topic_name,
                partitions=self._settings.kafka_topic_partitions,
                replication_factor=self._settings.kafka_topic_replication_factor,
            )
        except TopicAlreadyExistsError:
            self._logger.info(
                "topic_already_exists",
                topic=topic_name,
            )

    def close(self) -> None:
        if self._admin is not None:
            self._admin.close()
            self._admin = None