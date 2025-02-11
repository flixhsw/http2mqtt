import asyncio
import aiohttp
import yaml
import argparse
from jsonpath_ng import jsonpath, parse
import aiomqtt
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', 
                    encoding='utf-8',
                    level=logging.DEBUG)
    
class RestServerHandler():
    def __init__(self, config):
        self.url = config['url']
        self.configCyclicRequests = {}
        for endpointCfg in config.get('cyclic_requests', []):
            self.configCyclicRequests[endpointCfg['endpoint']] = endpointCfg
        if len(self.configCyclicRequests) == 0:
            logger.info(self.url + ': No cyclic requests configured')

        self.configTriggeredRequests = {}
        for forwardCfg in config.get('triggered_requests', []):
            self.configTriggeredRequests[forwardCfg['topic']] = forwardCfg
        if len(self.configTriggeredRequests) == 0:
            logger.info(self.url + ': No triggered requests configured')

    async def pollEndpoint(self, session, mqttClient, endpoint):
        if len(self.configCyclicRequests) == 0:
            return
        
        logger.info('Starting cyclic requests for ' + endpoint)
        while True:
            await asyncio.gather(self.read_and_publish(session, mqttClient, endpoint),
                                 asyncio.sleep(self.configCyclicRequests[endpoint]['cycle'] ))
    
    async def read_and_publish(self, session, mqttClient, endpoint):
        logger.debug('GET ' + self.url + endpoint)
        
        try:
            async with session.get(endpoint) as response:
                data = await response.json()
            logger.debug(data)
        except Exception as err:
            logger.warning('exception %s' % type(err) + ' on ' + self.url + endpoint)
            data = None

        tasks = []
        for topic_config in self.configCyclicRequests[endpoint]['topics']:
            jsonpath_expr = parse(topic_config['json_path'])
            match = jsonpath_expr.find(data)
            if match:
                message = match[0].value
                tasks.append(mqttClient.publish(topic_config['topic'], str(message)))

        await asyncio.gather(*tasks)

    async def forwardTopics(self, session, mqttClient):
        if len(self.configTriggeredRequests) == 0:
            return

        for topic in self.configTriggeredRequests.keys():
            logger.info('Subscribing to ' + topic)
            await mqttClient.subscribe(topic)
 
        async for message in mqttClient.messages:
            topic = str(message.topic)
            if topic in self.configTriggeredRequests:
                endpoint = self.configTriggeredRequests[topic]['endpoint']
                method = self.configTriggeredRequests[topic].get('method', 'GET').upper()
                then = self.configTriggeredRequests[topic].get('then_read', [])
                retries = self.configTriggeredRequests[topic].get('retries', 0)
                params = self.configTriggeredRequests[topic].get('params', {})

                for key, value in params.items():
                    params[key] = value.format(payload=message.payload.decode('utf-8'))

                if method not in ['GET', 'POST']:
                    logger.error('Invalid method ' + method + ' for topic ' + topic + '. Use GET or POST.')

                try:
                    async with session.request(method, endpoint, params=params) as response:
                        logger.info(response.url)
                        logger.info(response.status)
                        data = await response.text()
                        logger.info(data)
                except Exception as err:
                    logger.warning(method + ' ' + self.url + endpoint + ' with params=' + str(params))
                    logger.warning('exception %s' % type(err) + ' on ' + self.url + endpoint)
                    data = None

                for endpoint in then:
                    await self.read_and_publish(session, mqttClient, endpoint)


    async def run(self, mqttClient):
        timeout = aiohttp.ClientTimeout(total=5)
        logger.info('Starting session with ' + self.url)
        async with aiohttp.ClientSession(self.url, timeout=timeout) as session:
            tasks = [ self.forwardTopics(session, mqttClient) ]
            for endpoint in self.configCyclicRequests.keys():
                tasks.append(self.pollEndpoint(session, mqttClient, endpoint))

            await asyncio.gather(*tasks)


async def main(config_path):
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    
    hostname = config['mqtt'].get('hostname')
    port = config['mqtt'].get('port', 1883)
    user = config['mqtt'].get('user', None)
    password = config['mqtt'].get('password', None)
    identifier = config['mqtt'].get('identifier', None)

    logger.info('Starting MQTT connection to ' + hostname + ':' + str(port))
    async with aiomqtt.Client(hostname, port, username=user, password=password, identifier=identifier) as mqttClient:
        tasks = []
        for config in config['rest_server']:
            handler = RestServerHandler(config)
            tasks.append(handler.run(mqttClient))

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='REST to MQTT bridge')
    parser.add_argument('config', type=str, help='Path to the configuration file')
    args = parser.parse_args()

    asyncio.run(main(args.config))