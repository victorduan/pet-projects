#/usr/bin
# -*- coding: utf-8 -*-

import mechanize
import re
import smtplib
import traceback
import sys
import logging
import os
import config
from bs4 import BeautifulSoup

def SendSMS(data):
	recipients = config.recipients
	server = smtplib.SMTP( "smtp.gmail.com", 587 )
	server.starttls()
	server.login( config.gmail_user, config.gmail_pass )
	for email_address in recipients:
		server.sendmail( config.gmail_user, email_address, data )

def CheckValue(wager, threshold=150):
	regex = re.compile("[\d,]+")
	matches = regex.findall(wager)
	if len(matches) == 2:
		matches[0] = matches[0].replace(",", "")
		matches[1] = matches[1].replace(",", "")
		if (int(matches[0]) > threshold or int(matches[1]) > threshold):
			return True
	
	return False


customerID = config.customerID
password = config.password
row_tracker = ''
row_counter = 0
bets_dict = {}
path = os.path.dirname(os.path.realpath(__file__))

logging.basicConfig(format='%(asctime)s | %(levelname)s | %(filename)s | %(message)s', level=logging.INFO, filename=path+'/log.log')

params = { 'customerID' : customerID, 'password' : password}

logging.info("Reading list...")
if os.path.isfile(path+'/list.txt'):
	with open(path+'/list.txt') as f:
		id_list = f.readlines()
	f.close()
	id_list = ["".join(x.split()) for x in id_list]
else:
	id_list = []

logging.debug("List contents: {0}".format(id_list))


br = mechanize.Browser()
br.open(config.page1)
assert br.viewing_html()

logging.info("Going to page: {0}".format(config.page1))

# Log in
br.select_form(name='Agent_Login_Form')
br.form['customerID'] = customerID
br.form['password'] = password
resp = br.submit()

print resp.geturl()

# Navigate past the next page
br.select_form(nr=1)
resp2 = br.submit()

print resp2.geturl()
logging.info("Going to page: ".format(config.page2))
# Navigate to the bets page
br.open(config.page2)
assert br.viewing_html()

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
			data = "#" + bet['ticket_id']+'\n'
			data += bet['wager_type']+'\n'
			data += '\n'.join(bet['wager'])+'\n'
			data += bet['sport_name']+'\n'
			data += bet['bet_size']
			try:
				if CheckValue(bet['bet_size']):
					logging.info("Sending data: {0}".format(data))
					# Send SMS
					SendSMS(data)
					print data
					logging.info("Updating list...")
					with open(path+'/list.txt', 'a') as f:
						f.write(bet['ticket_id']+'\n')
					f.close()
				else:
					print "Bets not large enough"
					logging.info("Bet not large enough: {0}".format(data))
					logging.info("Updating list...")
					with open(path+'/list.txt', 'a') as f:
						f.write(bet['ticket_id']+'\n')
					f.close()
			except Exception, err:
				traceback.print_exc(file=sys.stdout)
				logging.exception(err)

	if not matches:
		logging.info("No new bets were found.")
		print "No new bets were found."
else:
	print "No bets found."

