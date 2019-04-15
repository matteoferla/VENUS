__description___ = """
The input page checks clientside whether the inputs exist or are valid.

Then an ajax request (gene_check) is triggered in which the gene is matched to an ID thanks to a database of synonyms. It is fast enough that this step could be implement on change as many pages do.
Parallelly, a bunch of tasks are kicked off to assemble the data using the method `parallel_parse_protein`.

The the mutation is checked &mdash;TBImpl.

Then every second, the status_check ajax request asks what is not done. Unfortunately, session cannot store objects so the thread names are stored.
Whereas it is true that Thread names can be assigned, the importance is their uniqueness. So a rather complex scheme is in place:

    request.session['threads'] = {Unique_thread_name: thread_description_that_makes_sense, ...}

"""

import sys, traceback, random
from pyramid.view import view_config
from pyramid.renderers import render_to_response
# from Tracker_analyser import Variant
# Variant.from_pickle = False

from protein import ProteinLite, Mutation

from mako.template import Template
from mako.lookup import TemplateLookup

import json, threading, time, os
from pprint import PrettyPrinter
pprint = PrettyPrinter().pprint

namedex = json.load(open('data/human_prot_namedex.json', 'r'))
#seqdex = json.load(open('data/human_prot_seqdex.json', 'r'))
#genedex = json.load(open('data/human_prot_genedex.json', 'r'))

@view_config(route_name='analyse', renderer="../templates/results.mako")
def analyse_view(request):
    def error_response(msg):
        request.session['status']['step'] = 'complete'
        return render_to_response('json', {'error': msg}, request)

    if 'status' in request.session and request.session['status']['step'] != 'complete':
        print('Double analysis error')
        return error_response('You have an ongoing analysis already for {g} {m}, which is at {s} step.'.format(g=request.session['status']['gene'],
                                                                                                          m=request.session['status']['mutation'],
                                                                                                          s=request.session['status']['step']))
    else:
        request.session['status'] = {'gene': '<parsing gene>', 'step': 'starting', 'mutation': '<parsing mutation>'}  # step = starting | complete | failed
    try:
        if request.POST['gene'] not in namedex:
            print('Invalid gene error')
            return error_response('The gene name is not valid.')
        ### load protein
        uniprot = namedex[request.POST['gene']]
        request.session['status']['gene'] = uniprot
        protein = ProteinLite(uniprot=uniprot).load()
        ### parse mutations
        mutation = Mutation(request.POST['mutation'])
        request.session['status']['mutation'] = str(mutation)
        if not protein.check_mutation(mutation):
            print('protein mutation discrepancy error')
            return error_response(protein.mutation_discrepancy(mutation))
        ### wait for all to finish
        protein.complete()
        protein.predict_effect(mutation)
        request.session['status']['step'] = 'complete'
        return {'protein': protein, 'mutation': protein.mutation}
    except NotImplementedError as err:
        print('actual error')
        traceback.print_exc(limit=3, file=sys.stdout)
        return error_response(str(err)+' gave a '+err.__name__)

@view_config(route_name='task_check', renderer="json")
def status_check_view(request):
    if 'status' not in request.session:
        print('missing job error')
        return {'error': 'No job found'}
    elif request.session['status']['step'] != 'complete':
        return {'status': 'You have an ongoing analysis for {g} {m}, which is at {s} step.'.format(g=request.session['status']['gene'],
                                                                                                   m=request.session['status']['mutation'],
                                                                                                   s=request.session['status']['step'])}
    else:
        return {'status': 'Analysis for {g} {m} is complete.'.format(g=request.session['status']['gene'],
                                                                     m=request.session['status']['mutation']),
                'complete': True}

@view_config(route_name='random', renderer="json")
def random_view(request):
    choices = list(namedex.items())
    random.shuffle(choices)
    for k,v in choices: ## in future once fully parsed. .choice
        if os.path.exists(os.path.join(ProteinLite.settings.pickle_folder,v+'.p')):
            protein = ProteinLite(uniprot=v).load()
            if protein.pdbs:
                pdb = protein.pdbs[0]
            elif protein.swissmodel:
                pdb = protein.swissmodel[0]
            else:
                continue
            i = random.randint(int(pdb['x'])-1, int(pdb['y'])-1)
            try:
                return {'name': k, 'mutation': 'p.{f}{i}{t}'.format(f = protein.sequence[i], i = i+1, t = random.choice(Mutation.aa_list))}
            except IndexError:
                print('Error... PDB numbering is wonky!')

import requests as rq

@view_config(route_name='xpost', renderer="string")
def talk_to_michelanglo(request):
    """
    This is an experimental option. What if there was a single user db?
    The problem is that the cookie on one App is different from the other.
    Two layers of security. A shared environment variable and REMOTE_ADDR 127.0.0.1
    Do note that the apps are in different venvs.
    """
    if request.user: #this feature is not open to unregistered users.
        data = {'username': request.user.name,
                'code': os.environ['SECRETCODE'],
                'description': request.params['description'],
                'title': request.params['title'],
                'protein': request.params['protein']
        }
        return rq.post('http://localhost:8088/venus', data=data).content.decode('utf-8')




