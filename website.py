import os
import peewee
import tornado.template as template
import tornado.web as web
import tornado.websocket as websock

def local_path(dir):
    return os.path.join(os.path.dirname(__file__), dir)

class MainHandler(web.RequestHandler):
    def initialize(self, ref_object):
        self.rise = ref_object

    def get(self):
        from pydeepool import Delegate, Voter
        loader = template.Loader(local_path('html'))
        context = {}
        context['delegate'] = self.rise.delegates.get_by_public_key(self.rise.config['key'])['delegate']
        context['share'] = self.rise.config['votershare']
        context['supporters'] = Voter.select().count()
        delegate = Delegate.get(id=1)
        context['blockpayout'] = self.rise.config['blockpayout']
        context['avevote'] = delegate.current_average / context['supporters']
        self.write(loader.load('index.html').generate(**context))

class AcntHandler(web.RequestHandler):
    def initialize(self, ref_object):
        self.rise = ref_object

    def get(self, addr=None):
        acnt = self.rise.accounts.get_account(addr)
        delegate = self.rise.accounts.get_delegates(addr)
        if acnt['success'] == False:
            self.write('Account not found.')
            return
        
        if delegate['success'] == False or len(delegate['delegates']) <= 0:
            self.write('You aren\'t voting for anyone.')
            return
        
        if delegate['delegates'][0]['publicKey'] != self.rise.config['key']:
            self.write('You aren\'t voting for this delegate.')
            return
        
        db = peewee.SqliteDatabase('voters.db')
        from pydeepool import Voter, Contrib, Delegate
        from decimal import Decimal
        context = {}
        context['acnt'] = acnt['account']
        context['delegate'] = delegate['delegates'][0]
        context['stats'] = Delegate.get(id=1)
        context['voter'] = Voter.get(address=addr)
        context['share'] = self.rise.config['votershare']/100
        context['voterperc'] = int(context['voter'].current_ave)/context['stats'].current_average
        weight = context['voter'].current_ave / context['stats'].current_average
        deliver = Decimal(context['stats'].current_forge * context['share'])
        stats = context['stats']
        #get latest reward
        reward = self.rise.blocks.get_blocks(limit=1)['blocks'][0]['reward']
        forged_blocks = Decimal(stats.current_forge / reward)
        forged_perday = Decimal(self.rise.config['blockpayout'] / 101)
        context['payout'] = deliver * weight
        context['estpay'] = (context['payout']) / (forged_blocks/forged_perday)
        loader = template.Loader(local_path('html'))        
        self.write(loader.load('account.html').generate(**context))
       
def webapp(rise):
    return web.Application([
        (r"/", MainHandler, dict(ref_object=rise)),
        (r"/addr/(\d+R)/", AcntHandler, dict(ref_object=rise)),
    ],  static_path=local_path('assets'))
