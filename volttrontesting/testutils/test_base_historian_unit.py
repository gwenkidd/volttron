import datetime
from datetime import timedelta
import os
from shutil import rmtree
from time import sleep
from pathlib import Path

import pytest
from pytz import UTC

from volttrontesting.utils.utils import AgentMock
from volttron.platform.agent.base_historian import BaseHistorianAgent, Agent


agent_data_dir = os.path.join(os.getcwd(), os.path.basename(os.getcwd()) + ".agent-data")
os.makedirs(agent_data_dir, exist_ok=True)
CACHE_NAME = str(Path(agent_data_dir).joinpath("backup.sqlite"))

HISTORIAN_DB = "./data/historian.sqlite"


def test_base_historian_agent_should_filter_duplicates(base_historian_agent):
    # Add duplicates to queue
    # Uniqueness is defined as a combination of topic and timestamp
    # Thus a duplicate has the same topic and timestamp
    for num in range(40, 43):
        base_historian_agent._capture_record_data(
            peer=None,
            sender=None,
            bus=None,
            topic="duplicate_topic",
            headers={
                "Date": "2015-11-17 21:24:10.189393+00:00",
                "TimeStamp": "2015-11-17 21:24:10.189393+00:00",
            },
            message=f"last_duplicate_{num}",
        )

    # Add a unique record to queue
    base_historian_agent._capture_record_data(
        peer=None,
        sender=None,
        bus=None,
        topic="unique_record_topic_1",
        headers={
            "Date": "2020-11-17 21:21:10.189393+00:00",
            "TimeStamp": "2020-11-17 21:21:10.189393+00:00",
        },
        message="unique_record_1",
    )

    # Since this is a unit test, we have to "manually start" the base_historian to get the workflow going
    base_historian_agent.start_process_thread()
    # Adding sleep to ensure that all data gets publised in the cache before testing
    sleep(3)

    expected_to_publish_list = [
        {
            '_id': 1,
            'headers': {'Date': '2015-11-17 21:24:10.189393+00:00',
                        'TimeStamp': '2015-11-17 21:24:10.189393+00:00',
                        'time_error': False},
            'meta': {},
            'source': 'record',
            'timestamp': datetime.datetime(2015, 11, 17, 21, 24, 10, 189393, tzinfo=UTC),
            'topic': 'duplicate_topic',
            'value': 'last_duplicate_40'
        },
        {
            '_id': 4,
            'headers': {'Date': '2020-11-17 21:21:10.189393+00:00',
                        'TimeStamp': '2020-11-17 21:21:10.189393+00:00',
                        'time_error': False},
            'meta': {},
            'source': 'record',
            'timestamp': datetime.datetime(2020, 11, 17, 21, 21, 10, 189393, tzinfo=UTC),
            'topic': 'unique_record_topic_1',
            'value': 'unique_record_1'
        }
    ]

    # Whenever data comes in to the BaseHistorian, it is published to a Queue to be be processed by the publishing thread as soon as possible.
    # As new data is published to the Queue, it will be saved to the cache. Data is batched into groups up to the value of `submit_size_limit` 
    # (which defaults to 1000). As the data becomes available in the cache, the BaseHistorian agent will check for duplicate items in the order 
    # they were added to the cache and omit them from the list to be published. Leaving only a list of unique items to be published, which in
    # this case, is shown by the expected_to_publish_list.  
    assert base_historian_agent.last_to_publish_list == expected_to_publish_list


BaseHistorianAgent.__bases__ = (AgentMock.imitate(Agent, Agent()),)


class BaseHistorianAgentTestWrapper(BaseHistorianAgent):
    def __init__(self, **kwargs):
        self.last_to_publish_list = ""
        super(BaseHistorianAgentTestWrapper, self).__init__(**kwargs)

    def publish_to_historian(self, to_publish_list):
        self.report_all_handled()
        self.last_to_publish_list = to_publish_list


@pytest.fixture()
def base_historian_agent():
    base_historian = BaseHistorianAgentTestWrapper()
    # default is 300 seconds or 5 minutes; setting to 1 second so tests don't take so long
    base_historian._retry_period = 1.0
    # When SQLHistorian is normally started on the platform, this attribute is set.
    # Since the SQLHistorian is being tested without the volttron platform,
    # this attribute must be set so that the test can run
    base_historian._max_time_publishing = timedelta(float(1))

    yield base_historian
    # Teardown
    # the backup database is an sqlite database with the name "backup.sqlite".
    # the db is created if it doesn't exist; see the method: BackupDatabase._setupdb(check_same_thread) for details
    # also, delete the historian database for this test, which is an sqlite db in folder /data
    if os.path.exists("./data"):
        rmtree("./data")
    if os.path.exists(CACHE_NAME):
        os.remove(CACHE_NAME)
    if os.path.exists(agent_data_dir):
        os.rmdir(agent_data_dir)
