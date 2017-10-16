#!/usr/bin/env python
import time
import peewee
import tornado.ioloop

from datetime import datetime
from rise import RiseAPI
from website import webapp

db = peewee.SqliteDatabase('voters.db')

rise = RiseAPI('http://127.0.0.1:5555')
delay = 30.0 #Set the delay to 30 seconds to capture all blocks.
pub_key = ''
pub_address = ''
secret_key = ''
secondsecret_key = None
payout_hours = 24
forged = 0
started = datetime.now()
min_payout = 1
active = {}
voter_share = 80
public_pool = True
whitelist = []
payout_addr = None
blockpayout = 2880
devdonation = 0

class Delegate(peewee.Model):
    id = peewee.IntegerField(primary_key=True)
    start_height = peewee.IntegerField(default=0)
    current_height = peewee.IntegerField(default=0)
    current_forge = peewee.IntegerField(default=0)
    total_payout = peewee.IntegerField(default=0)
    current_average = peewee.IntegerField(default=0)
    last_average = peewee.IntegerField(default=0)


    class Meta:
        database = db

class Voter(peewee.Model):
    joined = peewee.DateTimeField()
    payout = peewee.IntegerField()
    total_paid = peewee.IntegerField()
    current_ave = peewee.DecimalField()
    address = peewee.CharField(unique=True)
    
    class Meta:
        database = db
        
    def __init__(self, acnt=None):
        super(Voter, self).__init__()
        self.contributions = {}
        self.joined = datetime.now()
        self.payout = 0
        self.total_paid = 0
        self.current_ave = 0
        if acnt:
            self.address = acnt['address']

    def contribute(self, current_height, acnt, start_height, runDB=True):
        self.contributions[current_height] = int(acnt['balance'])
        level = (current_height - start_height)+1
        contrib = sum( [ n for c, n in self.contributions.items() ] )
        self.current_ave = contrib / level
        
        if runDB:
            self.save()
            c = Contrib(voter=self, balance=acnt['balance'], height=current_height, start=start_height)
            c.save()

        
class Contrib(peewee.Model):
    voter = peewee.ForeignKeyField(Voter, related_name='dbcontribs')
    balance = peewee.IntegerField()
    height = peewee.IntegerField()
    start =  peewee.IntegerField()
    
    class Meta:
        database = db    

def boot_db():
    global active
    first_height = None
    current_height = None
    #Check if there's an existing DB. If there is, pickup where we left off.
    for voter in Voter.select():
        for c in voter.dbcontribs.select():
            if first_height:
                first_height = min(first_height, c.height)
                current_height = max(current_height, c.height+1)
            else:
                first_height = c.height
                current_height = c.height
            voter.contribute(c.height, {'balance': c.balance}, c.start, False)
        active[voter.address] = voter
    
    return (first_height, current_height)

#this function is called every day.
# **scope is all the current variables from the main loop. They wont be modifiable except for Voter class objects.
# Return True to reset payout averages. If you don't return True people who join on the 100th height will have a 0 average at 100x weight of anything else.
def payout(**scope):
    ##Calcualte Payoute
    global rise, delay, pub_key, pub_address, secret_key
    global payout_hours, forged, started, min_payout, active
    global voter_share, devdonation, secondsecret_key

    delegate = rise.delegates.get_by_public_key(pub_key)['delegate']
    start_height = scope['start_height']
    current_height = scope['current_height']
    total_average_votes = sum([a.current_ave for k, a in active.items()])
    
    discrepency = total_average_votes - int(delegate['vote'])
    fee = 10000000
    fees = 0
    
    net = forged
    
    del_share = (100 - devdonation - voter_share) / 100
    share = voter_share / 100
    dev_share = devdonation / 100
    
    deliver = net * share
    delg_pay = net * del_share 
    dev_pay = net * dev_share
    paid = 0
    
    if dev_pay > 0:
        rise.transactions.send(secret=secret_key, amount=dev_pay - fee, recipient_id='3151592665681648214R', second_secret=secondsecret_key)
        paid += dev_pay
        fees += fee
    if payout_addr:
        rise.transactions.send(secret=secret_key, amount=delg_pay - fee, recipient_id=payout_addr, second_secret=secondsecret_key)
        paid += delg_pay
        fees += fee

    for addr, acnt in active.items():
        weight = acnt.current_ave / total_average_votes
        owed = deliver * weight
        
        acnt.payout += owed
        acnt.total_paid += owed
        if acnt.payout/100000000 >= min_payout:
            to_pay = owed - fee
            rise.transactions.send(secret=secret_key, amount=to_pay, recipient_id=acnt.address, second_secret=secondsecret_key)
            acnt.payout = 0
            paid += to_pay
            fees += fee
    delegate = Delegate.get(id=1)
    delegate.last_average = sum([a.current_ave for k, a in active.items()])
    delegate.total_payout += deliver
    delegate.save()
    print("\nPayout Info For Blocks %d-%d" % (start_height, current_height))
    print("\t%d Accounts Paid." % len(active) )
    print("\tPaid out %d Rise with %d in fees." % ((paid / 100000000), fees / 100000000))
    print("\tDelegate earned %d Rise." % (del_pay / 100000000 ))
    print("\tYou donated %d to the developer!\n" % (dev_pay / 100000000))
    return True

def process_blocks(start):
    global rise, delay, pub_key, pub_address, secret_key, payout_hours, forged, started, delegate_donation, devdonation, min_payout, active, payout_addr, whitelist
    PULSE_PER_MINUTE = 60/delay
    PULSE_PER_HOUR = PULSE_PER_MINUTE * 60
    PULSE_PER_DAY = PULSE_PER_HOUR * 24
    #start_height = 341788 #testing.
    newest_height = int(rise.blocks.get_blocks(limit=1)['blocks'][0]['height'])
    if start[0]:
        start_height = min(start[0], newest_height)
    else:
        start_height = int(rise.blocks.get_blocks(limit=1)['blocks'][0]['height'])
    current_height = start_height if not start[1] else start[1]
    print("Starting at block height %d" % current_height)
    last_block = False
    #Persistance. If the script goes off every still gets paid.
    delegate, created = Delegate.get_or_create(id=1)
    delegate.start_height = start_height
    forged = delegate.current_forge
    pulse_count = 0
    
    last_pulse = datetime.now()
    #Infintite Loop to process blocks and maintain a list of supporters.
    while(True):
        #pulse_count += 1
        pulse_count = current_height - start_height +1
        if pulse_count % blockpayout == 0:
            if payout(**locals()):
                start_height = current_height
                active = {}
                Voter.delete().execute()
                Contrib.delete().execute()
                delegate.start_height = current_height
                delegate.current_forge = 0
                delegate.save()
                forged = 0
        if pulse_count >= PULSE_PER_DAY:
            pulse_count = 0

        #now snapshots the time letting all contrib entries to share the same stamp.
        now = datetime.now()
        #This lets us know how long since the last pulse happened. It makes sure it's really close to 30 seconds.
        diff = now - last_pulse
        #Keep delay from being negative.
        #Delay for 30 seconds to grab blocks.
        pulse = delay-diff.seconds
        #The if check lets us play catchup if we're behind.
        if current_height >= newest_height:
            time.sleep(max(0, pulse))
        
        latest_block = rise.blocks.get_blocks(height=current_height)
        if not latest_block['blocks']: #Next block not Risen yet. Continue
            last_pulse = now
            continue

        latest_block = latest_block['blocks'][0]
        delegate.current_average = sum([a.current_ave for k, a in active.items()])

        
        #Credit voters with contributions.
        accounts = rise.delegates.get_voters(pub_key)['accounts']

        for acnt in accounts:
            if public_pool or acnt['address'] in whitelist:
                if acnt['address'] not in active:
                    active[acnt['address']] = Voter(acnt)
                v = active[acnt['address']]
                #Credit voter at this timestamp with current balance.
                v.contribute(current_height, acnt, start_height)
        current_height += 1
        delegate.current_height = current_height
        delegate.save()
        if latest_block['generatorId'] != pub_address:
            last_pulse = now
            continue
        
        forged += int(latest_block['reward'])
        delegate.current_forge = forged
        delegate.save()
        last_pulse = now

def get_username():
    global rise
    while True:
        print("Please enter a Username:")
        username = input()
        if rise.delegates.get_by_username(username)['success'] == False:
            print("That username already exists.")
        else:
            break
    return username

def get_minpayout():
    while True:
        print("Please enter the minimum payout.")
        payout = input()
        if not payout.isdigit():
            print("It must be a whole, positive number.")
        else:
            break
    return int(payout)

def get_votershares():
    while True:
        print("Please enter a number between 1-100 for the percentage you wish to share with your voters.")
        share = input().strip()
        if not share.isdigit() or int(share) > 100 or int(share) < 1:
            continue
        break
    return int(share)

def get_blockpayout():
    while True:
        print("Please enter the number of blocks between payouts. 2880 is 24 hours.")
        share = input().strip()
        if not share.isdigit():
            continue
        break
    return int(share)


def get_payoutaddr():
    while True:
        print("Enter a payout address to send whatever your delegate makes. Leave blank to leave them.")
        addr = input()
        if rise.accounts.get_account(addr)['success'] == False and len(addr) > 0:
            print("That account address cannot be found.")
            continue
        break;
    if len(addr) <= 0:
        addr = None
    return addr

def get_secrets():
    print("Please enter you secret key.")
    secret = input()
    print("Please enter your second secret key. If you don't have one leave blank, hit enter.")
    secondsecret = input()
    if len(secondsecret) <= 0:
        secondsecret = None
    return (secret, secondsecret)
    
    
if __name__ == '__main__':
    import json, sys, argparse
    parser = argparse.ArgumentParser(description='PyDeePool is a Rise Delegates Pool. It was created in the wake of discovering abuse by pool hoppers. It tracks the balance of your voters at every block height. It averages out that based on a 2879 block period (24 hours). People who get in, in the 1400th block will have half the weight as someon in for the whole period.\n\n\tTo run first run the script with no arguments to generate a new config file. Use --run to start the payout script. If you want a webserver to display statistics, run the command again but with --web, this will start the webserver.')
    parser.add_argument('--run', help='Begins running the payout script.',  action="store_true")
    parser.add_argument('--web', help='Begins the webserver.',  action="store_true")
    parser.add_argument('--add', help='Add to the whitelist', metavar='RISEADDR')
    parser.add_argument('--remove', help='Remove from the whitelist', metavar='RISEADDR')
    parser.add_argument('--display', help='Show a list of address on the Whitelist',  action="store_true")
    parser.add_argument('--config', help='Shows your current config settings.',  action="store_true")
    parser.add_argument('--config-public', help='Sets your pool to a public pool. Pays everyone that votes for you.', action='store_true')
    parser.add_argument('--config-private', help='Sets your pool to private. Only address on the white list are paid out.', action='store_true')
    parser.add_argument('--config-key', help='Set the public key for the script.', metavar='PUBLICKEY')
    parser.add_argument('--config-blockpayout', help='Set the number of blocks between payouts. 2880 is roughly 24H.', metavar='BLOCKS')
    parser.add_argument('--config-addr', help='Set the public address for the script.', metavar='PUBLICADDRESS')
    parser.add_argument('--config-minpayout', help='Set the minimum payout per voter.', metavar='RISE', type=int)
    parser.add_argument('--config-votershare', help='Sets your voter share to N%%.', metavar='PERCENT', type=int)
    parser.add_argument('--config-secret', help='Sets your secret key for the account.', metavar='SECRETKEY')
    parser.add_argument('--config-devdonation', help='Sets how much you donate to the dev. Default is 0.5%%', metavar='SECRETKEY')
    parser.add_argument('--config-secondsecret', help='Sets your second secret key for the account.', metavar='SECRETKEY')
    parser.add_argument('--config-webport', help='Sets the port your webserver listens on. Default 8989', metavar='PORT', type=int)
    parser.add_argument('--config-payoutaddr', help='Sets the address to payout the delegates share.', metavar='PORT', type=int)
    
    args = parser.parse_args()

    config = {'address': None,
              'secret': None,
              'secondsecret': None,
              'username': None,
              'key': None,
              'minpayout': 1,
              'votershare': 80,
              'public': True,
              'webport': 8989,
              'blockpayout': 2880,
              'devdonation': 0.5,
              }
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("This is your first time running this script. Enter the following information to get going!\n\nEnter your Public Address: ",)
        address = input()
        acnt = rise.accounts.get_account(address)
        if acnt['success'] == False:
            print("This account could not be found. Would you like to create an account? [Y/N]")
            res = input()
            if input.lower() == 'n':
                print("Exiting")
                sys.exit(1)
            while True:
                print("To create an account please enter a valid BIP39 mnemonic code more than 12 words, less than 100 characters. Generate one at wallet.rise.com. If you choose register there, just put the public address.")
                secret = input()
                acnt = rise.accounts.get_account(secret)
                if acnt['success']:
                    break
                acnt = rise.account.open(secret)
                secondsecret = None
                if acnt['success']:
                    break
        else:
            secret, secondsecret = get_secrets()
            
            
        if not acnt['account']['publicKey']:
            result = rise.accounts.generate_public_key(secret)
            if result['success'] == False:
                print("Failed to get a public key. Exiting.")
                sys.exit(1)
            pubkey = result['publicKey']
        else:
            pubkey = acnt['account']['publicKey']
            
        delegate = rise.delegates.get_by_public_key(pubkey)
        if delegate['success'] == False:
            print("You aren't a delegate. You need to register as a delegate. Would you like to register as a delegate? (25 Rise) [Y/N]")
            response = input()
            if response.lower() == 'n':
                print("Delegation registration is required to run a delegate pool. Exiting")
                sys.exit(1)
                
            username = get_username().strip()
            result = rise.delegates.enable(secret, username, secondsecret)
            
            if result['success'] == True:
                print("You have successfully registered as a delegate.")
            else:
                print("Registration has failed with the given information. Exiting.")
                sys.exit(1)
        
        else:
            username = delegate['delegate']['username']
            
        config['key'] = pubkey
        config['secret'] = secret
        config['secondsecret'] = secondsecret
        config['username'] = username
        config['address'] = address

        config['minpayout'] = get_minpayout()
        config['votershare'] = get_votershares()
        config['address'] = delegate['delegate']['address']
        config['payoutaddr'] = get_payoutaddr()
        config['blockpayout'] = get_blockpayout()
            
        with open('config.json', 'w') as f:
            json.dump(config, f)
        print("Your delegate has been setup and configured. Use python3 ./pydeepool.py --run to begin payout script. Strongly suggested if you're not running from a local terminal you use 'nohup python3 ./pydeepool --run &' to run. You are setup running a PUBLIC pool so you pay everyone out. To switch to private 'python3 ./pydeepool.py --config-private' will switch you to a private pool.")
        db.create_tables([Voter, Contrib, Delegate])
        sys.exit(1)

    pub_key = config['key']
    pub_address = config['address']
    min_payout = int(config['minpayout'])
    voter_share = int(config['votershare'])
    secret_key = config['secret']
    public_pool = config['public']
    payout_addr = config['payoutaddr']
    blockpayout = config['blockpayout']
    devdonation = config['devdonation']
    secondsecret_key = config['secondsecret']
    if not public_pool:
        try:
            with open('whitelist.json', 'r') as f:
                whitelist = json.load(f)
        except FileNotFoundError:
            with open('whitelist.json', 'w') as f:
                whitelist.append(payout_addr)
                json.dump(whitelist, f)

    if args.display:
        if public_pool:
            print("\nYou're currently running a PUBLIC pool and anyone voting for you gets a payout.\n")
        else:
            print("\nYou're currently running a PRIVATE pool and only the following addresses will get payouts.\n")
        for w in whitelist:
            print("\t%s" % w)
        print("")
        sys.exit(1)

    if args.add:
        if rise.accounts.get_account(args.add)['success'] == True:
            print("Adding %s to the whitelist." % args.add)
            whitelist.append(args.add)
            with open('whitelist.json', 'w') as f:
                json.dump(whitelist, f)
        else:
            print("That address is not valid.")
            sys.exit(1)

    if args.run or args.config:
        print("\n\tVoters Share: %s%%\n\tPublic Pool: %s\n\tMinimum Payout: %s Rise.\n\tAccount %s\n\tKey %s\n" % (voter_share, public_pool, min_payout, pub_address, pub_key))
        if args.run:
            if not config['key'] or not config['secret'] or not config['address']:
                print("\n\tYou must set your public key, public address and secret key to start.\n")
                parser.print_help()
                sys.exit(1)
            start = boot_db()
            process_blocks(start)
        sys.exit(1)
    
    if args.web:
        print("Starting webapp.")
        #You can only pass one ref_object to tornado so we're going to hogtie the config to the api
        rise.config = config
        app = webapp(rise)
        app.listen(config['webport'])
        tornado.ioloop.IOLoop.current().start()
        print("Exiting")
        sys.exit(1)
        
    def CONFIG(var, val):
        config[var] = val
        with open('config.json', 'w') as f:
            json.dump(config, f)
        print("%s updated to %s" % (var, val))
    
    if args.config_addr:
        CONFIG('address', args.config_addr)
        sys.exit(1)
    if args.config_key:
        CONFIG('key', args.config_key)
        sys.exit(1)
    if args.config_secret:
        CONFIG('secret', args.config_secret)
        sys.exit(1)
    if args.config_minpayout:
        CONFIG('minpayout', args.config_minpayout)
        sys.exit(1)
    if args.config_votershare:
        CONFIG('votershare', args.config_votershare)
        sys.exit(1)
    if args.config_webport:
        CONFIG('webport', args.config_webport)
        sys.exit(1)
    if args.config_private:
        CONFIG('public', False)
        sys.exit(1)
    if args.config_public:
        CONFIG('public', True)
        sys.exit(1)        
    if args.config_secondsecret:
        CONFIG('secondsecret', True)
        sys.exit(1)        
    if args.config_blockpayout:
        CONFIG('blockpayout', True)
        sys.exit(1)        
    if args.config_devdonation:
        try:
            args.config_devdonation = Decimal(args.config_devdonation)
        except decimal.InvalidOperation:
            print("It must be a number, between 0.00 and 99.9")
            sys.exit(1)
        if args.config_devdonation < 0 or args.config_devdonation > 99.9:
            print("It must be a number between 0.00 and 99.9")
            sys.exit(1)

        CONFIG('devdonation', True)
        sys.exit(1)        
        

    parser.print_help()
