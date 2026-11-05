from pathlib import Path

from data_retrieval_agent.agent import DataRetrievalAgent
from data_retrieval_agent.config import AgentSettings


def test_agent_is_disabled_by_default():
    agent = DataRetrievalAgent(settings=AgentSettings(), services={}, approved_sources=set())
    assert agent.ready is False


def test_source_availability_requires_approval_and_real_files(tmp_path):
    customer_path = tmp_path / "customer.parquet"
    customer_path.touch()
    metadata = tmp_path / "customer.json"
    metadata.touch()
    segmentation = tmp_path / "segmentation"
    segmentation.mkdir()
    (segmentation / "consumer_assignments.parquet").touch()
    (segmentation / "model_metadata.json").touch()
    anomaly_path = tmp_path / "anomaly.parquet"
    anomaly_path.touch()
    anomaly_model = tmp_path / "anomaly.joblib"
    anomaly_model.touch()

    agent = DataRetrievalAgent(
        settings=AgentSettings(),
        services={
            "customer_gold_path": customer_path,
            "customer_metadata_path": metadata,
            "segmentation_output_dir": segmentation,
            "anomaly_dataset_path": anomaly_path,
            "anomaly_model_path": anomaly_model,
        },
        approved_sources={"customer_gold", "segmentation_2018", "anomaly_synthetic_2019"},
    )
    assert agent.available_sources() == {"customer_gold", "segmentation_2018", "anomaly_synthetic_2019"}

    unapproved = DataRetrievalAgent(
        settings=AgentSettings(), services={"customer_gold_path": customer_path}, approved_sources=set()
    )
    assert unapproved.available_sources() == set()
