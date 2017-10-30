import json
import os
from multiprocessing import dummy
from itertools import islice
import requests

import newspaper
from helpers import timeit, LemmaTokenizer
from plotter import plot
nlp_api = 'https://lbs45qdjea.execute-api.us-west-2.amazonaws.com/prod/newscraper'
scrape_api = 'https://x9wg9drtci.execute-api.us-west-2.amazonaws.com/prod/article_get'


class LambdaWhisperer:
    json_results = []

    def __init__(self):
        pass

    @timeit
    def scrape_api_endpoint(self, text_):
        response = json.loads(requests.put(scrape_api, data=text_).text)
        if 'message' in response:
            return ''

        return response

    @timeit
    def nlp_api_endpoint(self, text_):
        response = json.loads(requests.put(nlp_api, data=text_).text)
        LambdaWhisperer.json_results.append(response)

        return response

    @timeit
    def send(self, articles):

        cleaned = ' '.join(LemmaTokenizer(articles))
        return self.nlp_api_endpoint(cleaned)


class GetSite:

    def __init__(self, url, name_clean=None, limit=15):
        self.API = LambdaWhisperer()
        self.limit = limit
        # Test url
        self.url = self.https_test(url)

        # Get list of newspaper.Article objs
        self.article_objs = self.get_newspaper()
        # Threadpool for getting articles

        self.article_objs = islice(self.article_objs, self.limit)
        self.articles = self.articles_gen()

        self.API.send(self.articles)

        if not name_clean:
            self.name_clean = self.strip()
        else:
            self.name_clean = name_clean

        if self.API.json_results:
            self.dump()
            # self.draw()

        self.show()

    def show(self):
        plot(self.API.json_results, url=self.url, name_clean=self.name_clean)

    @timeit
    def articles_gen(self):

        url_list = [a.url for a in self.article_objs]
        res = list(dummy.Pool(self.limit).map(self.API.scrape_api_endpoint, url_list))

        return ' '.join(res)

    def draw(self):
        plot(LambdaWhisperer.json_results, self.url, self.name_clean)

    def strip(self):
        return ''.join([
            c for c in self.url.replace('https://', '').replace('http://', '').replace('www.', '')
            if c.isalpha()
        ])

    def dump(self):

        j_path = './static/{}.json'.format(self.name_clean)
        with open(j_path, 'w') as fp:
            json.dump(LambdaWhisperer.json_results, fp, sort_keys=True)
        assert os.path.exists(j_path)

    @timeit
    def test_url(self, url_):
        try:
            if requests.get(url_).ok:
                return url_
            else:
                return False
        except requests.exceptions.ConnectionError:
            return False

    @timeit
    def https_test(self, url):
        if 'http://' or 'https://' not in url:
            url = self.test_url('https://' + url) or self.test_url('http://' + url)
            print(url)
            if not url:
                print('No website here!')
                return
            return url

    @timeit
    def get_newspaper(self):

        try:
            src = newspaper.build(
                self.url,
                fetch_images=False,
                request_timeout=2,
                limit=self.limit,
                memoize_articles=False)

        except Exception as e:
            print(e)
            print(self.url)
            return "No articles found!"
        print(len(src.articles))
        print(src.articles[0].url)

        return src.articles

    def get_articles(self, url):
        try:
            article = newspaper.Article(url)
            article.download()
            article.parse()
        except newspaper.article.ArticleException:
            return ''
        print(article.title)
        return article.text + ' ' + article.title


if __name__ == '__main__':

    @timeit
    def run(url, sample_articles=None):
        GetSite(url, sample_articles)
        print(LambdaWhisperer.json_results)

    run('foxnews.com')