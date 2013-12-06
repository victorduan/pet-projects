#/usr/bin
# -*- coding: utf-8 -*-

import os
import json
import traceback
import smtplib
import sys
import re
import config
from datetime import date
today = date.today().strftime("%m/%d/%y")

import mechanize
from bs4 import BeautifulSoup

path = os.path.dirname(os.path.realpath(__file__))

def LoadConfig():
	if os.path.isfile(path+'/forum_config.json'):
		with open(path+'/forum_config.json') as json_file:
			json_dict = json.load(json_file)
		json_file.close()
		return json_dict
	else:
		print "No config file found. Exiting."
		sys.exit()

  
def SendSMS(data):
	recipients = config.recipients
	server = smtplib.SMTP( "smtp.gmail.com", 587 )
	server.starttls()
	server.login( config.gmail_user, config.gmail_pass )
	for email_address in recipients:
		server.sendmail( config.gmail_user, email_address, data.encode('utf-8') )

def ProcessThread(url, follow_user):
	page = 1 # Assume every thread has 1 page
	max_page = 0
	next_url = url + '&page=' + str(page)

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
	br.open(next_url)
	html = br.response().get_data()

	soup = BeautifulSoup(html)

	main_table = soup.find_all('table', attrs={"class": "forum"})[0]
	# Find pages
	nav_table = soup.find_all('table', attrs={"class": "threadnav-row"})[1]
	try:
		page_counter = nav_table.tr.find_all('td')[1].strong.contents[0]
		print page_counter
		regex = re.compile("\d$")
		max_page = int(regex.findall(str(page_counter))[0])
	except AttributeError:
		max_page = 1
		print "Only one page present"

	table_rows = main_table.find_all('tr')
	post_header = main_table.find_all('td', attrs={'class': 'forumhead'})[1].contents[0]

	print post_header

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
						data  = follow_user + "\n"
						data += post_header + " | " + post_number + "\n"
						data += post_time + "\n"
						data += re.sub(r'[\xa0]'," ",post_text)
						print data
						SendSMS(data)

						# Notify and log
						with open(path+'/forum.txt', 'a') as f:
							f.write(post_checker+'\n')
						f.close()


		except KeyError:
			print "Class not found. Skipping."


def FindRecentPosts(user, url):
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

		if data['user'].upper() == follow_user and data['date'] == today:
			if data['link'] not in json_dict:
				json_dict[data['link']] = {'user' : data['user'], 'post_count' : data['post_count']}
				posts_list.append(data)
			elif int(data['post_count']) > int(json_dict[data['link']]['post_count']):
				json_dict[data['link']] = {'user' : data['user'], 'post_count' : data['post_count']}
				posts_list.append(data)
			else:
				print "Nothing new posted in existing threads"

	print posts_list

	with open(path+'/recent_posts.json', 'w') as f:
		f.write(json.dumps(json_dict))
	f.close()

	return posts_list

if __name__ == "__main__":
	config_dict = LoadConfig()
	base_url = config_dict['base_url']

	for user in config_dict['users']:
		print "Checking user: %s" % user
		follow_user = user.upper()
		url = base_url + follow_user
		posts = []
		posts = FindRecentPosts(follow_user, url)

		print posts

		for post in posts:
			ProcessThread(post['link'], follow_user)

	
