# Shutterfly Share Site Downloader

Fork of the work [here](https://github.com/beaufour/shutterfly_sites_api) with important improvements to download more than 15 pictures from more than 25 albums. This project will become irrelevant tomorrow (3/27/23) but it's here so I don't lose the work I put into modifying it. Thanks [beaufour](https://github.com/beaufour) for doing most of this work!

# How to use

```
pip3 install -r requirements.txt
```

Open your Shutterfly Share Site with the Inspect Element window open. In the network tab, optionally filter by Filter/XHR and locate a query like in `refresh?site=xyz`. In the headers tab of that query, scroll down to cookie in the Request Headers section, and isolate your `ShrAuth` from within that wall of cookie text. Use this to run the program like so:

```
python3 main.py --site [site name] --token [your ShrAuth token] --directory [where to download]
```

And let it run! If you get a network error, go through the steps to get a new ShrAuth token and rerun the script.
