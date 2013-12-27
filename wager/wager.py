#/usr/bin
# -*- coding: utf-8 -*-

import mechanize
import re
import smtplib
import yaml
import sys
import json
import logging
import os
import config
from bs4 import BeautifulSoup

path = os.path.dirname(os.path.realpath(__file__))

def SendSMS(data):
	recipients = config_dict['recipients'] # Should be a list or a string (if one email)
	server = smtplib.SMTP( "smtp.gmail.com", 587 )
	server.starttls()
	server.login( config.gmail_user, config.gmail_pass )
	server.sendmail( config.gmail_user, recipients, data )

def CheckValue(wager, threshold=50):
	regex = re.compile("[\d,]+")
	matches = regex.findall(wager)
	if len(matches) == 2:
		matches[0] = matches[0].replace(",", "")
		matches[1] = matches[1].replace(",", "")
		if (int(matches[0]) > threshold or int(matches[1]) > threshold):
			return True
	
	return False

def LoadConfig():
	if os.path.isfile(path+'/wager_config.json'):
		with open(path+'/wager_config.json') as json_file:
			json_dict = json.load(json_file)
		json_file.close()
		return json_dict
	else:
		logging.error("No config file found. Exiting.")
		sys.exit()

# Logging file details
from logging import config
with open(path+'/logging.yml') as f:
	D = yaml.load(f)
logging.config.dictConfig(D)

# Import config after logging config
import config

if __name__ == "__main__":
	config_dict = LoadConfig()

	for user in config_dict['users']:
		customerID = user['customerID']
		password = user['password']
		friendly_name = user['friendly_name']
		row_tracker = ''
		row_counter = 0
		bets_dict = {}
		
		params = { 'customerID' : customerID, 'password' : password}

		logging.info("Reading list for %s..." % customerID)
		if os.path.isfile(path+'/'+customerID+'-list.txt'):
			with open(path+'/'+customerID+'-list.txt') as f:
				id_list = f.readlines()
			f.close()
			id_list = ["".join(x.split()) for x in id_list]
		else:
			id_list = []

		logging.debug("List contents: {0}".format(id_list))


		br = mechanize.Browser()
		br.open(config_dict['urls']['login_url'])
		assert br.viewing_html()

		logging.info("Going to page: {0}".format(config_dict['urls']['login_url']))

		# Log in
		br.select_form(name='Agent_Login_Form')
		br.form['customerID'] = customerID
		br.form['password'] = password
		resp = br.submit()

		# URL Should be page2
		redirect = resp.geturl()

		if redirect == config_dict['urls']['validation_url']:
			# Navigate past the next page
			br.select_form(nr=1)
			resp2 = br.submit()

		logging.info("Going to page: %s" % config_dict['urls']['bets_url'])
		# Navigate to the bets page
		br.open(config_dict['urls']['bets_url'])

		html = br.response().get_data()

		soup = BeautifulSoup(html)
		bets_table = soup.find_all('table')[len(soup.find_all('table'))-1]
		bets = bets_table.find_all('tr')

		for bet in bets:
			attrs = bet.attrs

			if 'class' in attrs:
				if attrs['class'][0] != 'GameHeader':
					tr_class = bet.get('class')[0] # Should be Tr0, Tr1, etc

					if tr_class != row_tracker:
						row_tracker = tr_class
						row_counter += 1
						index = str(row_counter)
						bets_dict[index] = { 'wager' : []}

					ticket_id = bet.find_all('b')
					if len(ticket_id):
						regex = re.compile("\d+-\d")
						new_ticket = regex.findall(str(ticket_id[0]))[0]
						# Add ticket_id
						bets_dict[index]['ticket_id'] = new_ticket

						columns = bet.find_all('td')
						sport_name = ' '.join(columns[1].contents[0].strip().split())
						# Add sport name
						bets_dict[index]['sport_name'] = sport_name

						columns[2].contents[0] = re.sub(r'[\xa0]'," ",columns[2].contents[0]) # Mysterious whitespace
						columns[2].contents[0] = re.sub(r'[\xbd]',".5",columns[2].contents[0]) # Fix for half points
						wager = columns[2].contents[0].strip()
						# Add wager
						bets_dict[index]['wager'].append(wager)


						bet_size = bet.find_all('th')[2].contents[0].strip()
						bets_dict[index]['bet_size'] = bet_size

						temp = bet.find_all('th')[1]
						regex = re.compile("[0-9aA-zZ\s\(\)-]+<br>")
						wager_type = regex.findall(str(temp))[0]
						# Add wager type: Spread, Parlay, etc
						bets_dict[index]['wager_type'] = wager_type.strip().replace("<br>","") 

					else:
						columns = bet.find_all('td') 
						columns[2].contents[0] = re.sub(r'[\xa0]'," ",columns[2].contents[0]) # Mysterious whitespace
						columns[2].contents[0] = re.sub(r'[\xbd]',".5",columns[2].contents[0]) # Fix for half points
						wager = columns[2].contents[0].strip()
						# Add wager
						bets_dict[index]['wager'].append(wager)

		if len(bets_dict):
			matches = 0
			for key, bet in bets_dict.items():
				if bet['ticket_id'] not in id_list:
					matches += 1 # Increment the match counter if one is found
					logging.info("Ticket {0} is new".format(bet['ticket_id']))
					data  = friendly_name + " (" + customerID + ")" + '\n'
					data += "#" + bet['ticket_id']+'\n'
					data += bet['wager_type']+'\n'
					data += '\n'.join(bet['wager'])+'\n'
					data += bet['sport_name']+'\n'
					data += bet['bet_size']
					try:
						if CheckValue(bet['bet_size']):
							logging.info("Sending data: {0}".format(data))
							# Send SMS
							SendSMS(data)
							logging.info("Updating list...")
							with open(path+'/'+customerID+'-list.txt', 'a') as f:
								f.write(bet['ticket_id']+'\n')
							f.close()
						else:
							logging.info("Bet not large enough: {0}".format(data))
							logging.info("Updating list...")
							with open(path+'/'+customerID+'-list.txt', 'a') as f:
								f.write(bet['ticket_id']+'\n')
							f.close()
					except Exception, err:
						logging.exception(err)

			if not matches:
				logging.info("No new bets were found.")
		else:
			logging.info("No bets found for user %s" % customerID)

