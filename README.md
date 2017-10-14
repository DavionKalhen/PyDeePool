# PyDeePool
Rise Vision Delegate Pool Software. Includes a hop-proof payout script, and website with live payout statistics updated every 30 seconds. To become a Delegate, you must have your own Rise.node setup. This script can walk you throug the process of signing up as a delegate and payout all your voters. You can have a public or private pool. Payout is based on wallet balances at every block height (roughly every 30 seconds).

# Setup
To setup, you must first have Python3, Tornado, SQLite3, and Rise-Py.

     sudo apt-get install python3
     sudo apt-get install virtualenv
     sudo apt-get install sqlite3
     sudo apt-get install python3-pip

Setup your virtualenv

     virtualenv env
     source env/bin/activate
     
Install your Python libs.

    pip3 install sqlite3client
    pip3 install tornado
    

Grab the Rise API.

     git clone https://github.com/RiseVision/rise-py.git
     cp -f ./rise-py/rise ./;rm -fr ./rise-py

Running the script for the first time will prompt you for answers, and will configure for you.

    @localhost:~/github/PyDeePool$ python3 pydeepool.py --run
    This is your first time running this script. Enter the following information to get going!

    Enter your Public Address:
    3511748430431975976R
    Please enter you secret key.
    asdf
    Please enter your second secret key. If you don't have one leave blank, hit enter.

    Please enter the minimum payout.
    1
    Please enter a number between 1-100 for the percentage you wish to share with your voters.
    80
    Enter a payout address to send whatever your delegate makes. Leave blank to leave them.
    
    Please enter the number of blocks between payouts. 2880 is 24 hours.
    2880
    Your delegate has been setup and configured. Use python3 ./pydeepool.py --run to begin payout script.
    Strongly suggested if you're not running from a local terminal you use
    'nohup python3 ./pydeepool --run &' to run. You are setup running a PUBLIC pool so you pay everyone out.
    To switch to private 'python3 ./pydeepool.py --config-private' will switch you to a private pool.

      
