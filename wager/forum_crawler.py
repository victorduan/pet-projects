#/usr/bin
# -*- coding: utf-8 -*-

import os
import json
import smtplib
import sys
import logging
import yaml
import re
import requests
from datetime import date, timedelta
today = date.today().strftime("%m/%d/%y")
yesterday = (date.today()-timedelta(1)).strftime("%m/%d/%y")

import mechanize
from bs4 import BeautifulSoup

path = os.path.dirname(os.path.realpath(__file__))

# Logging file details
from logging import config
with open(path+'/logging.yml') as f:
	D = yaml.load(f)
logging.config.dictConfig(D)

# Import config after logging config
import config

def LoadConfig():
	if os.path.isfile(path+'/forum_config.json'):
		with open(path+'/forum_config.json') as json_file:
			json_dict = json.load(json_file)
		json_file.close()
		return json_dict
	else:
		logging.error("No config file found. Exiting.")
		sys.exit()

  
def SendSMS(data):
	recipients = config_dict['recipients']
	server = smtplib.SMTP( "smtp.gmail.com", 587 )
	server.starttls()
	server.login( config.gmail_user, config.gmail_pass )
	for email_address in recipients:
		logging.debug("Sending: {0} to {1}".format(data, email_address))
		server.sendmail( config.gmail_user, email_address, data.encode('utf-8') )

def GetBitlyLink(url):
	token = config_dict["bitly"]["token"]
	endpoint = config_dict["bitly"]["endpoint"]
	params = {
		'access_token' 	: token,
		'longUrl'		: url
	}
	r = requests.get(endpoint, params=params)
	if r.status_code == 200:
		logging.debug(r.content)
		return json.loads(r.content)['data']['hash']
	else:
		logging.error(r.content)
		return ""

def ProcessThread(url, follow_user):
	page = 1 # Assume every thread has 1 page
	max_page = 0
	runLoop = True

	# List format should be:
	# User|URL|Post#
	if os.path.isfile(path+'/forum.txt'):
		with open(path+'/forum.txt') as f:
			id_list = f.readlines()
		f.close()
		id_list = ["".join(x.split()) for x in id_list]
	else:
		id_list = []  

	br = mechanize.Browser()

	while runLoop:
		next_url = url + '&page=' + str(page)
		logging.info("Opening: %s" % next_url)
		br.open(next_url)
		html = br.response().get_data()

		soup = BeautifulSoup(html)

		main_table = soup.find_all('table', attrs={"class": "forum"})[0]
		# Find pages
		nav_table = soup.find_all('table', attrs={"class": "threadnav-row"})[1]
		try:
			page_counter = nav_table.tr.find_all('td')[1].strong.contents[0]
			regex = re.compile("\d$")
			max_page = int(regex.findall(str(page_counter))[0])
			page += 1
			if page > max_page:
				runLoop = False
		except AttributeError:
			# Stop the loop
			runLoop = False

		table_rows = main_table.find_all('tr')
		post_header = main_table.find_all('td', attrs={'class': 'forumhead'})[1].contents[0]

		for i in range(len(table_rows)):
			css_soup = BeautifulSoup(str(table_rows[i]))
			try:
				node_attrs = css_soup.tr['class']
				if str(node_attrs[0]) == 'sp-info':
					links = table_rows[i].find_all('a')
					username = links[0].contents[0]
					if username.upper() == follow_user:

						post_content = table_rows[i+1].find_all('td', attrs={"class": "forumpost-post"})[0]

						post_number = post_content.div.div.strong.contents[0]
						post_content.find_all('div', attrs={"class": "right"})[0].decompose()

						post_time = post_content.find_all('div', attrs={"class": "posted"})[0].contents[0]
						post_content.find_all('div', attrs={"class": "posted"})[0].decompose()

						post_text = ' '.join(post_content.findAll(text=True))

						# Check to see if the post has been collected already
						post_checker = str(username) + '|' + str(next_url) + '|' + str(post_number)
						if post_checker not in id_list:
							# Shorten the URL
							bitly_hash = GetBitlyLink(next_url)
							data  = follow_user + "\n"
							data += "bit.ly/"+bitly_hash+"\n"
							data += post_header + " | " + post_number + "\n"
							data += post_time + "\n"
							data += re.sub(r'[\xa0]'," ",post_text)
							logging.info("Data matched and ready to send: {0}".format(data))
							SendSMS(data)

							# Notify and log
							with open(path+'/forum.txt', 'a') as f:
								f.write(post_checker+'\n')
							f.close()


			except KeyError:
				print "Class not found. Skipping."


def FindRecentPosts(follow_user, url):
	# Read a JSON file to determine what threads to process
	# Don't want to reprocess a thread with no new posts
	if os.path.isfile(path+'/recent_posts.json'):
		with open(path+'/recent_posts.json') as json_file:
			json_dict = json.load(json_file)
		json_file.close()
	else:
		json_dict = {}

	# Hit the recent posts page
	br = mechanize.Browser()
	br.open(url)
	html = br.response().get_data()

	soup = BeautifulSoup(html)

	recent_posts = soup.find_all(id='tblRecentPosts')[0].find_all('tr')
	logging.debug(recent_posts)
	# List of posts that should be processed
	posts_list = []

	for row in recent_posts[1:]:
		r = row.find_all('td')

		# Find the date
		date = r[0].contents[0]

		# Find the count of posts
		post_count = r[3].contents[0]

		# Find the user posting
		# Add exception handling
		try:
			content = r[2].find_all('a')
			for link in content:
				user = link.contents[0]
		except IndexError:
			user = ''

		# Find the link to the post
		content = r[1].find_all('a')
		for link in content:
			post_link = link.get('href')

		data = {
			'date' : date,
			'user' : user,
			'link' : post_link,
			'post_count' : post_count
		}

		if data['user'].upper() == follow_user and (data['date'] == today or data['date'] == yesterday):
			if data['link'] not in json_dict:
				json_dict[data['link']] = {'user' : data['user'], 'post_count' : data['post_count']}
				posts_list.append(data)
			elif int(data['post_count']) > int(json_dict[data['link']]['post_count']):
				json_dict[data['link']] = {'user' : data['user'], 'post_count' : data['post_count']}
				posts_list.append(data)
			else:
				logging.info("No new post in thread: %s since last check" % url)

	with open(path+'/recent_posts.json', 'w') as f:
		f.write(json.dumps(json_dict))
	f.close()

	logging.debug("List of posts: {0}".format(posts_list))
	return posts_list

if __name__ == "__main__":
	config_dict = LoadConfig()
	base_url = config_dict['base_url']

	for user in config_dict['users']:
		logging.info("Checking user: %s" % user)
		follow_user = user.upper()
		url = base_url + follow_user
		logging.info("User URL: %s" % url)
		posts = []
		posts = FindRecentPosts(follow_user, url)

		for post in posts:
			logging.info("Checking thread: %s" % post['link'])
			ProcessThread(post['link'], follow_user)

	
