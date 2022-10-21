import copy
import os
import time
import sys
import requests
import json
import re
import argparse
import urllib.error
from bs4 import BeautifulSoup
from tqdm import tqdm
from colored import fg, bg, attr
from pprint import pprint
from datetime import datetime

parser = argparse.ArgumentParser(description="SmugMug Downloader")
parser.add_argument(
    "-s", "--session",
    help="session ID (required if user is password protected); log in on a web browser and paste the SMSESS cookie")
parser.add_argument(
    "-u", "--user", help="username (from URL, USERNAME.smugmug.com)", required=True)
parser.add_argument("-o", "--output", default="output/",
                    help="output directory")
parser.add_argument(
    "--albums",
    help="specific album names to download, split by $. Defaults to all. Wrap in single quotes to avoid shell variable substitutions. (e.g. --albums 'Title 1$Title 2$Title 3')")

args = parser.parse_args()

endpoint = "https://www.smugmug.com"

# Session ID (required if user is password protected)
# Log in on a web browser and copy the SMSESS cookie
SMSESS = args.session

cookies = {"SMSESS": SMSESS}

if args.output[-1:] != "/" and args.output[-1:] != "\\":
    output_dir = args.output + "/"
else:
    output_dir = args.output

output_dir = args.user + "/"

if args.albums:
    specificAlbums = [x.strip() for x in args.albums.split('$')]

officialAlbumFilename = "official_albums_%s.txt" % args.user


# Gets the JSON output from an API call
def get_json(url):
    num_retries = 5
    for i in range(num_retries):
        try:
            r = requests.get(endpoint + url, cookies=cookies)
            soup = BeautifulSoup(r.text, "html.parser")
            pres = soup.find_all("pre")
            return json.loads(pres[-1].text)
        except IndexError:
            print("ERROR: JSON output not found for URL: %s" % url)
            if i + 1 < num_retries:
                print("Retrying...")
            else:
                print("ERROR: Retries unsuccessful. Skipping this request.")
            continue
    return None


while 1:
    try:
        # Retrieve the list of albums
        print("Downloading album list...", end="")
        albums = get_json("/api/v2/folder/user/%s!albumlist" % args.user)
        if albums is None:
            print("ERROR: Could not retrieve album list.")
            sys.exit(1)

        # Quit if no albums were found
        try:
            albums["Response"]["AlbumList"]
        except KeyError:
            sys.exit(
                "No albums were found for the user %s. The user may not exist or may be password protected." % args.user)

        albumsToDownload = copy.deepcopy(albums)
        albumsToDownload["Response"]["AlbumList"] = []


        def generateOfficialAlbums(albums_arg):
            if not os.path.isfile(officialAlbumFilename):
                with open(officialAlbumFilename, "w") as outfile:
                    for album_for in albums_arg["Response"]["AlbumList"]:
                        outfile.write(album_for["Uri"] + "\n")


        def isAlbumAlreadyDownloaded(album_arg):
            with open(officialAlbumFilename) as file:
                if album_arg["Uri"] not in file.read():
                    print('Nouvel album !')
                    pprint(album_arg)
                    albumsToDownload["Response"]["AlbumList"].append(album_arg)
                else:
                    with open("pouet.txt", "a") as testjojo:
                        testjojo.write(album_arg["Uri"] + "\n")


        def addAlbumToAlreadyDownloaded(album_arg):
            with open(officialAlbumFilename, "a") as outfile:
                outfile.write(album_arg["Uri"] + "\n")


        # Pour le premier lancement on stock tous les albums
        generateOfficialAlbums(albums)

        # Pour les itérations suivantes on regarde si il n'y a pas d'autres albums à télécharger
        print(len(albums["Response"]["AlbumList"]))
        for album in albums["Response"]["AlbumList"]:
            isAlbumAlreadyDownloaded(album)

        albums = albumsToDownload

        if not albums["Response"]["AlbumList"]:
            print('Pas de nouvel album...')
            continue

        # Create output directories
        print("Creating output directories...", end="")
        for album in albums["Response"]["AlbumList"]:
            if args.albums:
                if album["Name"].strip() not in specificAlbums:
                    continue

            directory = output_dir + album["UrlPath"][1:]
            if not os.path.exists(directory):
                os.makedirs(directory)
        print("done.")


        def format_label(s, width=24):
            return s[:width].ljust(width)


        bar_format = '{l_bar}{bar:-2}| {n_fmt:>3}/{total_fmt:<3}'

        # Loop through each album
        for album in tqdm(albums["Response"]["AlbumList"], position=0, leave=True, bar_format=bar_format,
                          desc=f"{fg('yellow')}{attr('bold')}{format_label('All Albums')}{attr('reset')}"):
            if args.albums:
                if album["Name"].strip() not in specificAlbums:
                    continue

            album_path = output_dir + album["UrlPath"][1:]
            images = get_json(album["Uri"] + "!images")
            if images is None:
                print("ERROR: Could not retrieve images for album %s (%s)" %
                      (album["Name"], album["Uri"]))
                continue

            # Skip if no images are in the album
            if "AlbumImage" in images["Response"]:

                # Loop through each page of the album
                next_images = images
                while "NextPage" in next_images["Response"]["Pages"]:
                    next_images = get_json(
                        next_images["Response"]["Pages"]["NextPage"])
                    if next_images is None:
                        print("ERROR: Could not retrieve images page for album %s (%s)" %
                              (album["Name"], album["Uri"]))
                        continue
                    images["Response"]["AlbumImage"].extend(
                        next_images["Response"]["AlbumImage"])

                # Loop through each image in the album
                for image in tqdm(images["Response"]["AlbumImage"], position=1, leave=True, bar_format=bar_format,
                                  desc=f"{attr('bold')}{format_label(album['Name'])}{attr('reset')}"):
                    image_path = album_path + "/" + \
                                 re.sub('[^\w\-_\. ]', '_', image["FileName"])

                    pprint(image_path)
                    # TODO ICI
                    # image_path est égal à photoboothfun/Events/Hugh-Jackman-World-Tour-2019/Sydney-2nd-August-/1564734158.jpg et donc au chemin du fichier
                    # il faudrait stocker tous les image_path dans un gros tableau en supprimant le photoboothfun/
                    # faire le même tableau pour mon serveur (find . -type f : ./Events/Waikato/Whakatane-Hospital-Ball-2022/IMG_0443.JPG)
                    # et ensuite faire le diff le tableau API - tableau fichiers serveur
                    # dump le résultat (API - serveur) dans un .txt

                    # Skip if image has already been saved
                    if os.path.isfile(image_path):
                        continue

                    # Grab video URI if the file is video, otherwise, the standard image URI
                    largest_media = "LargestVideo" if "LargestVideo" in image["Uris"] else "LargestImage"
                    if largest_media in image["Uris"]:
                        image_req = get_json(image["Uris"][largest_media]["Uri"])
                        if image_req is None:
                            print("ERROR: Could not retrieve image for %s" %
                                  image["Uris"][largest_media]["Uri"])
                            continue
                        download_url = image_req["Response"][largest_media]["Url"]
                    else:
                        # grab archive link if there's no LargestImage URI
                        download_url = image["ArchivedUri"]

                    try:
                        r = requests.get(download_url)
                        with open(image_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=128):
                                f.write(chunk)
                    except UnicodeEncodeError as ex:
                        print("Unicode Error: " + str(ex))
                        continue
                    except urllib.error.HTTPError as ex:
                        print("HTTP Error: " + str(ex))

            addAlbumToAlreadyDownloaded(album)

        print("Completed download.")
    except Exception as e:
        now = datetime.now()
        with open("%s.err" % args.user, "a") as errorfile:
            errorfile.write(now.strftime("%d/%m/%Y %H:%M:%S") + ' ' + str(e) + "\n")
        time.sleep(60*2)
