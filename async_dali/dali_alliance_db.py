
import os
import sqlite3
from datetime import date
from typing import Iterable, NamedTuple
from xml.dom import Node, minidom

import aiohttp
import dateparser
from dom_query import select, select_all


class DaliAllianceProductRecord(NamedTuple):
    brand_name: str
    product_name: str
    dali_parts: Iterable
    initial_registration: date
    last_updated: date


class DaliAllianceProductDB:
    """Fetches information on a dali product from their online database based on GTIN, caching information in a local SQLITE3 database"""

    def __enter__(self):
        dir = os.path.expanduser("~/.dali")
        os.makedirs(dir, exist_ok=True)
        self.con = sqlite3.connect(dir + "/product.db")
        cur = self.con.cursor()
        cur.execute('create table if not exists products (gtin INT PRIMARY KEY, brand_name text, product_name text, dali_parts text, initial_registration text, last_updated text)')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.con.close()
        self.con = None


    def node_text(self, e):
        """
        Why isn't there a default way to get the text of an element?  This is my poor man's version which simply concatenates any text in any subnode.
        """
        txt = ""

        if e.nodeType == Node.TEXT_NODE:
            txt = txt + e.data
        if e.hasChildNodes:
            for c in e.childNodes:
                txt = txt + " " + self.node_text(c)
        return txt.strip()

    def cast_to_datetime(self, v):
        if isinstance(v, str):
            return dateparser.parse(v)
        return v

    def to_dict(self, res) -> DaliAllianceProductRecord:
        return DaliAllianceProductRecord(
            brand_name = res[0],
            product_name =  res[1],
            dali_parts = [int(x) for x in res[2].split(", ")],
            initial_registration = self.cast_to_datetime(res[3]).now().date(),
            last_updated =  self.cast_to_datetime(res[4]).now().date(),
        )

    async def fetch(self, gtin):
        cur = self.con.cursor()
        existing = cur.execute("SELECT brand_name, product_name, dali_parts, initial_registration, last_updated from products where gtin = ?", (gtin,)).fetchall()
        if len(existing) > 0:
            return self.to_dict(existing[0])
            
        # It wasn't in the database, so lets fetch it.
        new = await self.fetch_from_dali_alliance(gtin)
        if new:
            cur.execute("INSERT into products (gtin, brand_name, product_name, dali_parts, initial_registration, last_updated) values (?, ?, ?, ?, ?, ?)", (gtin, new[0], new[1], new[2], new[3], new[4],))
            self.con.commit()
            return self.to_dict(new)
            
        return None


    async def fetch_from_dali_alliance(self, gtin):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.dali-alliance.org/products?Default_submitted=1&advanced_field=&brand_id=&part_number=&product_name=&family_products%5B%5D=&registered%5B%5D=&obsolete%5B%5D=&product_id=&gtin={}&Default-submit=Search'.format(gtin)) as response:
                if response.status == 200:
                    txt = await response.text()
                    doc = minidom.parseString(txt)
                    # Find the product table
                    products = select_all(select(doc, 'table[class="product-listings"]'), "tbody > tr")
                    if len(products) > 0:
                        product_attrs = {}
                        for cell in select_all(products[0], "td"):
                            title = cell.getAttribute("data-title").lower()
                            if len(title) > 0:
                                product_attrs[title] = self.node_text(cell)
                        return (
                            product_attrs['brand name'], 
                            product_attrs['product name'], 
                            product_attrs['dali parts'], 
                            dateparser.parse(product_attrs['initial registration']), 
                            dateparser.parse(product_attrs['last updated']), 
                        )
        return None
                            
