"""
Websites with bias labels are scraped for articles. Each article gets stored with its
bias tags in a MongoDB table.

TODO: Address the class imbalance in the data. Some important categories (hate, for example)
    are underrepresented in the scraped article counts. In the past I have manually rescraped
    underrepresented tags, but it would be nice to have a sort of 'load balancer' to balance
    classes during the scraping.

"""

import itertools
import multiprocessing
import os
from multiprocessing.dummy import Pool
from time import sleep
import mongo_driver
import newspaper
from fake_useragent import UserAgent
import requests

os.environ['TLDEXTRACT_CACHE'] = '~/tldextract.cache'

config = newspaper.Config()
config.fetch_images = False
config.request_timeout = 5
config.memoize_articles = False


class NewsSource:

    def __init__(self, n_articles=1000):
        self.n_articles = n_articles
        pass

    def build(self, source):
        self._data = source
        self.categories = source['Category']
        self.url = self.test_https(source['url'].split('/')[0])
        self.source_url = source['url']
        if self.url == False:
            return
        self.get_links()
        self.build_meta()
        print(self.url)
        self.get_articles_controller()
        if self.source_obj.size() > 0:

            mongo_driver.insert('source_logs', self.meta)

    def test_https(self, url):

        def test_url(url_):
            try:
                return requests.get(url_).ok

            except requests.exceptions.ConnectionError:
                return False
            except requests.exceptions.TooManyRedirects:
                return False

        if 'http://' or 'https://' not in url:
            _url = 'https://' + url

            if test_url(_url) == False:
                _url = 'http://' + url
                if test_url(_url) == False:
                    return False
            url = _url
        return url

    def build_meta(self):
        self.meta = {}
        self.meta['Meta'] = {
            'Source': self.url,
            'Size': self.source_obj.size(),
            'Flags': self.categories,
            'Description': self.source_obj.description
        }

    def get_links(self):
        ua = UserAgent()
        self.source_obj = newspaper.build(
            self.url, browser_user_agent=ua.chrome, language='en', config=config)

    def get_articles_controller(self):
        articles = self.source_obj.articles
        if not self.source_obj.articles:
            return

        def get_articles(article):
            article_data = {}
            article.url = article.url.strip()

            try:
                article.download()

                article.parse()
            except Exception as e:
                print(e)
                return

            if article.title:
                # try:
                # article.nlp()
                # except:
                # article_data['keywords'] = article.keywords
                article_data['title'] = article.title
                article_data['text'] = article.text
                article_data['flags'] = self.categories
                article_data['source'] = self.url
                article_data['url'] = article.url
                article_data['source_url'] = self.source_url
                print(self.categories, '\t', article_data['source'], article_data['title'])
                mongo_driver.insert('articles', article_data)

        for x in articles:
            get_articles(x)


def go(source):
    NewsSource().build(source)


def threadpool(batch):

    with Pool(batch_size) as pool:

        x = pool.imap_unordered(go, batch)
        timeout_count = 0
        while True:
            try:
                x.next(timeout=120)
                timeout_count = 0
            except multiprocessing.context.TimeoutError:
                timeout_count += 1
                print('thread timeout!')
            except AttributeError as e:
                print(e)
            except StopIteration:

                print('\n', '!! batch finished !!', '\n')

                pool.terminate()

                break
            except EOFError:
                pass
            if timeout_count == 2:
                print('\n', '!! pool timed out !!', '\n')

                pool.terminate()

                break


def get_batch(batch_size):
    return itertools.islice(news_sources, batch_size)


if __name__ == '__main__':

    def get_news_sources():
        return mongo_driver.db['all_sources'].find()

    def urls_already_scraped(batch):
        return any([u['url'] in sources_already_scraped for u in batch])

    news_sources = get_news_sources()
    batch_size = 20

    sources = set()
    for i in get_news_sources():
        sources.add(i['url'])
    print("total num sources", len(sources))

    sources_already_scraped = set()
    for article in mongo_driver.db['articles'].find():
        url = article['source_url']
        sources_already_scraped.add(url)
    print("num sources already scraped", len(sources_already_scraped))

    print(mongo_driver.check_for_dups('articles', 'url'))

    def run_scraper():
        i = 1
        batch = list(get_batch(batch_size))
        while urls_already_scraped(batch):
            batch = list(get_batch(batch_size))
            i += 1
        print("Using batch %d" % i)
        threadpool(batch)

    for i in range(mongo_driver.db['all_sources'].count() // batch_size):
        run_scraper()
