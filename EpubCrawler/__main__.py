#!/usr/bin/env python3.7
# -*- coding: utf-8 -*-

from urllib.parse import urljoin
import sys
import json
from pyquery import PyQuery as pq
import time
from os import path
import re
from concurrent.futures import ThreadPoolExecutor
from GenEpub import gen_epub
from . import *
from .util import *
from .img import *
from .config import config

def get_toc_from_cfg():
    if config['list'] and len(config['list']) > 0:
        return config['list']
        
    if not config['url']:
        print('URL not specified')
        sys.exit()
        
    html = request_retry(
        'GET', config['url'],
        retry=config['retry'],
        headers=config['headers'],
        timeout=config['timeout'],
        proxies=config['proxy'],
    ).content.decode(config['encoding'], 'ignore')
    return get_toc(html, config['url'])
    
def get_toc(html, base):
    root = pq(html)
    
    if config['remove']:
        root(config['remove']).remove()
        
    el_links = root(config['link'])
    vis = set()
    
    res = []
    for i in range(len(el_links)):
        el_link = el_links.eq(i)
        url = el_link.attr('href')
        if not url:
            text = el_link.text().strip()
            res.append(text)
            continue
            
        url = re.sub(r'#.*$', '', url)
        if base:
            url = urljoin(base, url)
        if not url.startswith('http'):
            continue
        if url in vis: continue
        vis.add(url)
        res.append(url)
        
    return res
    
def get_article(html, url):
    root = pq(html)
    
    if config['remove']:
        root(config['remove']).remove()
        
    el_title = root(config['title']).eq(0)
    title = el_title.text().strip()
    el_title.remove()
    
    el_co = root(config['content'])
    co = '\r\n'.join([
        el_co.eq(i).html()
        for i in range(len(el_co))
    ])
    
    if config['credit']:
        credit = f"<blockquote>原文：<a href='{url}'>{url}</a></blockquote>"
        co = credit + co
        
    return {'title': title, 'content': co}
    
def tr_download_page(url, art, imgs):
    try:
        html = request_retry(
            'GET', url,
            retry=config['retry'],
            headers=config['headers'],
            timeout=config['timeout'],
            proxies=config['proxy'],
        ).content.decode(config['encoding'], 'ignore')
        art.update(get_article(html, url))
        art['content'] = process_img(
            art['content'], imgs,
            page_url=url,
            img_prefix='../Images/',
        )
        time.sleep(config['wait'])
    except Exception as ex:
        print(ex)

def main():
    global get_toc
    global get_article

    cfg_fname = sys.argv[1] \
        if len(sys.argv) > 1 \
        else 'config.json'
    if not path.exists(cfg_fname):
        print('please provide config file')
        return
        
    user_cfg = json.loads(open(cfg_fname, encoding='utf-8').read())
    config.update(user_cfg)
    if config['proxy']:
        proxies = {
            'http': config['proxy'],
            'https': config['proxy'],
        }
        config['proxy'] = proxies
    set_img_pool(ThreadPoolExecutor(config['imgThreads']))
    if config['external']:
        mod = load_module(config['external'])
        get_toc = getattr(mod, 'get_toc', get_toc)
        get_article = getattr(mod, 'get_article', get_article)
    
    toc = get_toc_from_cfg()
    articles = []
    imgs = {}
    if config['name']:
        articles.append({
            'title': config['name'],
            'content': f"<p>来源：<a href='{config['url']}'>{config['url']}</a></p>",
        })
    
    text_pool = ThreadPoolExecutor(config['textThreads'])
    hdls = []
    for url in toc:
        print(f'page: {url}')
        if url.startswith('http'):
            art = {}
            articles.append(art)
            hdl = text_pool.submit(tr_download_page, url, art, imgs)
            hdls.append(hdl)
        else:
            articles.append({'title': url, 'content': ''})
        
    for h in hdls: h.result()
    articles = [art for art in articles if art]
            
    gen_epub(articles, imgs)
    print('done...')
    
if __name__ == '__main__': main()
    