#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Description:
Usage:
    mapping_parser.py (--inGraph <str>) (--inPickle <str>) (--inJSON <str>) (--outDir <dir>) [--threshold <float>] [--verbose] [--debug]

Options:
    -h --help
    --inGraph <file>        input graph in GFA format
    --inPickle <file>       input dictionnaries from graph construction
    --inJSON <file>         input mapping in JSON format
    --threshold <float>     Threshold on the mapping score [default: 0.9]
    --outDir <dir>          Output directory
    --verbose
    --debug
"""

import sys

try:
    import docopt
except ModuleNotFoundError:
    print("mapping_parser.py requires module docopt, to install: pip3 install docopt")
    sys.exit()

from collections import defaultdict
import logging
import time
import json
import numpy as np
import pandas as pd
import re
import pickle
import os

def main():
    
    args = docopt.docopt(__doc__)
    verbose = args["--verbose"]
    debug = args["--debug"]
    graph_file = args["--inGraph"]
    mapping_file = args["--inJSON"]
    pickle_file = args["--inPickle"]
    output_dir = args["--outDir"]
    
    # logger
    global logger    
    setup_logger("logger", f"{output_dir}/logs.txt", verbose, debug)
    logger = logging.getLogger("logger")
    
    # Parse GFA
    global pangenome, d_clusters, d_genes, d_idt
    print("Parsing GFA file...")
    with Timer() as _t:
        pangenome = parse_graph(graph_file)
        d_clusters, d_genes, d_idt = generate_clusters_dict(pickle_file)
    all_time = _t.t
    logger.info(f"Graph parsing done in: {all_time}")
    logger.info(f'Number of unique genes : {len(d_genes)}')
    
    # Parse mapping file
    print("Parsing JSON file...")
    with Timer() as _t:
        reads, variants = parse_vgmpmap(mapping_file,thr=float(args["--threshold"]))
    all_time = _t.t
    logger.info(f"JSON parsing done in: {all_time}")
    
    # Compute abundances
    print("Computing abundances...")
    with Timer() as _t:
        d_abund, d_strains_abund, df = get_abundance(reads,variants)
        pickle_out = open(f"{output_dir}/res_geneslevel_{os.path.splitext(os.path.basename(mapping_file))[0]}.pickle","wb")
        pickle.dump(d_abund, pickle_out)
        pickle_out.close()
        pickle_out = open(f"{output_dir}/res_strainslevel_{os.path.splitext(os.path.basename(mapping_file))[0]}.pickle","wb")
        pickle.dump(d_strains_abund, pickle_out)
        pickle_out.close()
        df.to_csv(f"{output_dir}/res_strainslevel_{os.path.splitext(os.path.basename(mapping_file))[0]}.csv")
    all_time = _t.t
    logger.info(f"Abundances computation done in: {all_time}")
    
    
    
    
    
    
    
    
    
    
    
    
#    # Compute abundances
#    logger.info("Computing abundances...")
#    with Timer() as _t:
#        abund_nodes, abund_edges = get_abundance(reads)
#    all_time = _t.t
#    logger.info(f"Abundances computation done in: {all_time}")
#    
#    # Output results
#    abund_nodes.to_csv(f"{output_dir}/abundNodes_{sample_id}.csv")
#    abund_edges.to_csv(f"{output_dir}/abundEdges_{sample_id}.csv")
#    pickle_out = open(f"{output_dir}/variants_{sample_id}.pickle","wb")
#    pickle.dump(variants, pickle_out)
#    pickle_out.close()

###############################################################################

class Timer:
    def __enter__(self):
        self.t1 = time.time()
        return self
    
    def __exit__(self, *args):
        self.t2 = time.time()
        hours, rem = divmod(self.t2-self.t1, 3600)
        minutes, seconds = divmod(rem, 60)
        self.t = "{:0>2}:{:0>2}:{:05.2f}".format(int(hours), int(minutes), seconds)

class Node:
    
    def __init__(self, ID, sequence):
        self.ID = ID
        self.sequence = sequence
        self.pathsCrossed = defaultdict(list)
        self.previous = []
        self.next = []

class Path:
    
    def __init__(self, ID):
        self.ID = ID
        self.nodes = []

class Alignment:
    
    def __init__(self):
        self.nodes = []
    
    def addLen(self,length):
        self.len = length
    
    def addScore(self,score):
        self.score = score
    
    def addIdentity(self,identity):
        self.identity = identity
    
    def addVariants(self,variants):
        self.variants = variants


class Pangenome:

    def __init__(self):
        """ 
        initializes a graph object 
        """
        self.__graph_dict = {}
        self.__graph_dict["nodes"] = {}
        self.__graph_dict["paths"] = {}
    
    def add_path(self, path):
        """ 
        Add the path "path" to in self.__graph_dict, 
        """
        self.__graph_dict["paths"][path.ID] = path
 
    def get_path(self, path_id):
        """
        returns the path "path_id" of a graph
        """
        return self.__graph_dict["paths"][path_id]
    
    def paths(self):
        """ 
        returns the paths of a graph 
        """
        return list(self.__graph_dict["paths"].keys())
    
    def add_node(self, node):
        """ 
        Add the node "node" to in self.__graph_dict, 
        """
        self.__graph_dict["nodes"][node.ID] = node
    
    def edit_node(self, edit_type, key, value):
        """
        Add info to the node "key"
        edit_type can be "add_path", "add_next", "add_previous"
        """
        if edit_type == "add_path":
            path_id, t = value
            self.__graph_dict["nodes"][key].pathsCrossed[path_id].append(t)
        elif edit_type == "add_next":
            self.__graph_dict["nodes"][key].next.append(value)
        elif edit_type == "add_previous":
            self.__graph_dict["nodes"][key].previous.append(value)
        else:
            pass
    
    def get_node(self, node_id):
        """
        returns the node "node_id" of a graph
        """
        return self.__graph_dict["nodes"][node_id]
    
    def nodes(self):
        """ 
        returns the nodes of a graph 
        """
        return list(self.__graph_dict["nodes"].keys())

    def edges(self):
        """
        returns the edges of a graph
        """
        return self.__generate_edges()

    def __generate_edges(self):
        """ 
        A static method generating the edges of the graph "graph". 
        Edges are represented as sets with one (a loop back to the vertex) 
        or two vertices.
        """
        edges = []
        for node_id in self.__graph_dict["nodes"]:
            for neighbour_prev in self.__graph_dict["nodes"][node_id].previous:
                if {neighbour_prev, node_id} not in edges:
                    edges.append({node_id, neighbour_prev})
            for neighbour_next in self.__graph_dict["nodes"][node_id].next:
                if {neighbour_next, node_id} not in edges:
                    edges.append({node_id, neighbour_next})
        return edges


###############################################################################

def setup_logger(name, log_path, verbose, debug):
    l = logging.getLogger(name)
    formatter = logging.Formatter("%(asctime)s -- %(levelname)s -- %(message)s")
    fileHandler = logging.FileHandler(log_path, mode="w")
    fileHandler.setFormatter(formatter)

    l.setLevel(logging.DEBUG)
    l.addHandler(fileHandler)

    if verbose or debug:
        streamHandler = logging.StreamHandler(sys.stdout)
        streamHandler.setFormatter(formatter)
        l.addHandler(streamHandler)

def reverse_complement(dna):
    complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}
    return ''.join([complement[base] for base in dna[::-1]])

def parse_graph(graph_file):
    
    """
    PARSE GFA FILE
    From the gfa file, create a dictionary of the nodes and the paths in the graph.
    S lines contain node ID and its sequence
    P lines contain path ID, list of node ID with orientation and cover of the nodes
    L lines contain links between nodes
    node dictionary need to contain sequence, paths crossed with orientation, previous nodes and next nodes
    path dictionary need to contain sequence, node list, offset at the begining and the end
    """
    
    pangenome = Pangenome()
    with open(graph_file, 'r') as f:
        for line in f:
            line = line.strip().split('\t')
            # if line S, create node
            if line[0] == 'S':
                pangenome.add_node( Node(ID=line[1],sequence=line[2]) )
            # if line P, create paths and add paths infos in nodes
            elif line[0] == 'P':
                path_id = line[1]
                path = Path(ID=path_id)
                node_list = line[2].split(',')
                seq = ""
                for idx,node_info in enumerate(node_list):
                    ori = node_info[-1]
                    node_id = node_info.rstrip(ori)
                    node = pangenome.get_node(node_id)
                    pangenome.edit_node("add_path", node_id, (path_id, (idx,ori)))
                    path.nodes.append(node.ID)
                    if ori == "+":
                        seq += node.sequence
                    else:
                        seq += reverse_complement(node.sequence)
                path.sequence = seq
                pangenome.add_path(path)
            # if line L, get parents and children of each node
            elif line[0] == "L":
                node1 = pangenome.get_node(line[1])
                node2 = pangenome.get_node(line[3])
                if node2.ID not in node1.next:
                    pangenome.edit_node("add_next",node1.ID, node2.ID)
                if node1.ID not in node2.previous:
                    pangenome.edit_node("add_prev",node1.ID, node2.ID)
                
    return pangenome

def generate_clusters_dict(pickle_file):
    
    """
    Create all useful dictionaries
    d_clusters: key = cluster id, value = list of colored paths id
    d_genes: key = gene id, value = list of colored paths id
    d_idt: key = colored path id, value = cluster id + gene id
    """
    
    d_clusters = pickle.load( open( pickle_file, "rb" ) )
    
    d_genes = {}
    for cpath in pangenome.paths():
        nodelist = '-'.join(pangenome.get_path(cpath).nodes)
        if nodelist in d_genes:
            d_genes[nodelist].append(cpath)
        else:
            nodelist = '-'.join(pangenome.get_path(cpath).nodes[::-1])
            if nodelist in d_genes:
                d_genes[nodelist].append(cpath)
            else:
                d_genes[nodelist] = [cpath]
    
    d_idt = defaultdict(dict)
    for i in d_genes:
        for j in d_genes[i]:
            d_idt[j]['genes'] = i
    for i in d_clusters:
        for j in d_clusters[i]['genes_list']:
            d_idt[j]['cluster'] = i

    return d_clusters, d_genes, d_idt


def get_variants(mapping_node):
    for node in mapping_node['path']['mapping']:
        node_id = node['position']['node_id']
        offset = int(node['position'].get('offset',0))
        is_reverse = ('is_reverse' in node['position'])
        pos = len(pangenome.get_node(node_id).sequence)-1-offset if is_reverse else offset
        for edit in node['edit']:
            from_len = int(edit.get("from_length", 0))
            to_len = int(edit.get("to_length", 0))
            # subst or match
            if from_len == to_len: 
                # cas match
                if 'sequence' not in edit:
                    if is_reverse:
                        pos -= from_len
                    else:
                        pos += from_len
                # cas subst
                else:
                    for n in edit['sequence']:
                        yield (node_id, pos, n)
                        if is_reverse:
                            pos -= 1
                        else:
                            pos += 1
            # insert or del
            else:
                # cas deletion
                if 'sequence' not in edit:
                    for n in range(from_len):
                        yield (node_id, pos, ' ')
                        if is_reverse:
                            pos -= 1
                        else:
                            pos += 1
                # cas insertion
                else:
                    if is_reverse:
                        pos_bis = len(edit['sequence'])-1
                    else:
                        pos_bis = 0
                    for n in edit['sequence']:
                        if is_reverse: n = reverse_complement(n)
                        new_pos = str(pos-1)+'-'+str(pos)+'_'+str(pos_bis)
                        yield (node_id, new_pos, n)
                        if is_reverse:
                            pos_bis -= 1
                        else:
                            pos_bis += 1

def BFS(aln):
    
    subpath = aln['subpath']
    # step 1: initialize queue
    queue = []          # contains a set of nodes not yet traversed. 
    
    current_paths = {}  # in runtime, contains all reached paths. key = last path node id, value = tuple(path, read_len, score). 
                        # This enables to quickly retreive all paths that finish on a given node and to conserve the one(s) that minimize the alignment score 
    
    for start in range(len(subpath)): ## there can be several roots, loop over them
        try: ## for some reason aln['start'] can contain errors, "try" needed
            read_len = 0
            nb_match = 0
            nb_aligned = 0
            ## maybe the alignment can end with a node which has successor, we need to keep track of the position in the read along the alignment
            for node in subpath[start]['path']['mapping']:
                for edit in node["edit"]:
                    from_len = int(edit.get("from_length", 0))
                    to_len = int(edit.get("to_length", 0))
                    read_len += to_len
                    nb_match += to_len if from_len == to_len and "sequence" not in edit else 0
                    nb_aligned += min(from_len,to_len)
            ## end
            score = subpath[start].get("score", 0)                                    # score field is not displayed if = 0
            queue.append(start)                                                        # the queue contains only the current node 
            if start not in current_paths:                                             # init all paths/scores ending with the current node
                current_paths[start] = []                                    
            current_paths[start].append(([start],read_len,score,nb_match,nb_aligned)) # stores all paths that end with the start node.
        except IndexError: 
            continue
            
    ### WALK THE WHOLE SET OF NODES. 
    ### CONSERVE FOR EACH NODE THE BEST PATH (or PATHS in case of equality) SCORE
    while queue:

        current_node = queue.pop(0) ## pop first element of the queue 
        
        ### END OF THE PROCESS
        if 'next' not in subpath[current_node] or all(i[1]==len(aln['sequence']) for i in current_paths[current_node]): ## final paths obtained when there is no child or the length of the read is reached
            continue
        
        ### INSPECT ALL CHILDREN
        for child in subpath[current_node]['next']:
            
            ### ADD CHILD NODE IF NOT ALREADY IN THE QUEUE: 
            if child not in queue:                                              
                queue.append(child)
                
            read_len = 0
            nb_match = 0
            nb_aligned = 0
            ### keeping track of the position in the alignment
            for node in subpath[child]['path']['mapping']:
                for edit in node["edit"]:
                    from_len = int(edit.get("from_length", 0))
                    to_len = int(edit.get("to_length", 0))
                    read_len += to_len
                    nb_match += to_len if from_len == to_len and "sequence" not in edit else 0
                    nb_aligned += min(from_len,to_len)

            ### get child score (or 0 if attribute absent)
            child_score = subpath[child].get("score", 0)
                
            ### UPDATE THE SET OF PATHS 
            # 1/ For all detected paths that end with the current_node (retreived thanks to `current_paths`)
            # 2/ add all new paths with their scores
            # 3/ remove updated paths from the dictionary
            # 4/ conserve only the best path(s)
            if child not in current_paths:
                current_paths[child]=[]                                                 # init all paths/scores ending with the current node
            for (current_path, current_len, current_score, current_match, current_aligned) in current_paths[current_node]:                 # add all new paths with their scores
                updated_score = current_score + child_score
                updated_match = current_match + nb_match
                updated_aligned = current_aligned + nb_aligned                                                             # shortcut
                if len(current_paths[child])==0:
                    current_paths[child].append((current_path + [child], current_len + read_len, updated_score, updated_match, updated_aligned))        # create a new path that finish with the child node
                    continue                                                                                            # no need to update the paths ending with child, this is the first. 
                ### conserve only the best path(s)
                best_previous_score = current_paths[child][0][2]
                if updated_score > best_previous_score:                                                                 # The new path is better than all previous scores. Create a new set
                    current_paths[child]=[]                                                                             # for all paths ending on this child node
                    current_paths[child].append((current_path + [child], current_len + read_len, updated_score, updated_match, updated_aligned))        # create a new path that finish with the child node
                if updated_score == best_previous_score:                                                                # The new path is equal to all previous scores, add the new path
                    current_paths[child].append((current_path + [child], current_len + read_len, updated_score, updated_match, updated_aligned))        # create a new path that finish with the child node
                #if updated_score < best_previous_score: do nothing                                                     # The newly created path is worse than all previous ending on
                                                                                                                        # child. Nothing to be done

        current_paths.pop(current_node)      
                                                                           # No more path end with the current node
    final_paths = []
    for idx in current_paths: ## for each path among the current paths
        for tupl in current_paths[idx]: ## for each tuple we need to get back the list of nodes
            alignment = Alignment()
            variants = []
            for subpath_node in tupl[0]: ## parse each subpath_node
                for node in subpath[ subpath_node ]['path']['mapping']: # for each node get abundance
                    nodeID = node['position']['node_id']
                    abund = 0
                    for edit in node["edit"]:
                        from_len = int(edit.get("from_length", 0))
                        to_len = int(edit.get("to_length", 0))
                        abund += min(from_len,to_len)/len(pangenome.get_node(nodeID).sequence)
                    # if node already exists in the list, just add the abundance
                    current_node_list = [n[0] for n in alignment.nodes]
                    if nodeID in current_node_list:
                        node_loc = np.where(nodeID == np.array(current_node_list))[0][0]
                        alignment.nodes[node_loc] = (nodeID,alignment.nodes[node_loc][1]+abund)
                    else:
                        alignment.nodes.append((nodeID,abund))
                variants += [var for var in get_variants(subpath[subpath_node])]
            alignment.addVariants(variants)   
            alignment.addLen(tupl[1])
            alignment.addScore(tupl[2])
            alignment.addIdentity(tupl[3]/tupl[4])                 
            final_paths.append(alignment)
    return final_paths

def parse_vgmpmap(json_file, thr=0.9):
    
    """
    PARSE MAPPING JSON FILE
    First check all alignments from the same read
    Ignore read if no alignment score > thr
    Ignore read if multiple alignment score > thr
    
    score = scoring done by vg considering bonus for matches and penalty for mismatches and gap
    identity = Portion of aligned bases that are perfect matches, or 0 if no bases are aligned.
    """
    
    reads = defaultdict(dict) # clé read = id read contenant les différentes séquences (paired-end) contenant les alignements
    variants = defaultdict(dict)

    previous_read = ""
    
    with open(json_file, 'r') as aln_json:
        
        for line in aln_json:
            
            aln = json.loads(line)
            
            # parse only if the read has mapped
            if "subpath" not in aln:
                continue
            
            # get best path(s) for the alignement
            final_paths = BFS(aln)
            
            # if no path satisfying thr, skip, else add the paths
            new_score = final_paths[0].score/len(aln['sequence'])    
            if new_score >= thr:
                if aln['sequence'] not in reads[aln['name']]: 
                    reads[aln['name']][aln['sequence']] = final_paths
                else:               
                    current_score = reads[aln['name']][aln['sequence']][0].score/len(aln['sequence'])
                    # if new best score, replace
                    if new_score > current_score:
                        reads[aln['name']][aln['sequence']] = final_paths
                    # else add
                    else: 
                        if new_score == current_score:
                            reads[aln['name']][aln['sequence']] += final_paths
        
            # if all alignements checked for the current read, process variants
            if aln['name'] != previous_read and previous_read in reads:
                # but only if one alignment for the pair
                if all(len(reads[previous_read][seq]) == 1 for seq in reads[previous_read]):
                    for seq in reads[previous_read]:
                        for tupl in reads[previous_read][seq][0].variants:
                            if tupl[0] not in variants: variants[tupl[0]] = {}
                            if tupl[1] not in variants[tupl[0]]: variants[tupl[0]][tupl[1]] = {}
                            if tupl[2] not in variants[tupl[0]][tupl[1]]: variants[tupl[0]][tupl[1]][tupl[2]] = []
                            variants[tupl[0]][tupl[1]][tupl[2]].append(previous_read)

                
            previous_read = aln['name']
        
        # variants for the last line
        if aln['name'] != previous_read and previous_read in reads:
            if all(len(reads[previous_read][seq]) == 1 for seq in reads[previous_read]):
                for seq in reads[previous_read]:
                    for tupl in reads[previous_read][seq][0].variants:
                        if tupl[0] not in variants: variants[tupl[0]] = {}
                        if tupl[1] not in variants[tupl[0]]: variants[tupl[0]][tupl[1]] = {}
                        if tupl[2] not in variants[tupl[0]][tupl[1]]: variants[tupl[0]][tupl[1]][tupl[2]] = []
                        variants[tupl[0]][tupl[1]][tupl[2]].append(previous_read)
                    
    return reads,variants

def get_matching_path(node_list):
    
    """
    INPUT = a node list (from alignement)
    to speed the search we get the starting node of the alignment and search only on paths crossing this start node
    to speed the seach, we use the node position in the selected path and extend the list of nodes by the same length of the alignment
    there is a match if the seed+extend list is identical to the node list of the alignment
    OUPUT = list of paths where the node list match
    """
    
    found = []
    start_node = node_list[0]
    paths_sel = pangenome.get_node(start_node).pathsCrossed
    # for each path crossing the start node
    for path in paths_sel:
        # if the node is crossed more than one time by the same path
        for idx in pangenome.get_node(start_node).pathsCrossed[path]:
            # check identity of the nodes list (not forgetting the reverse complement case)
            if pangenome.get_path(path).nodes[idx[0]:idx[0]+len(node_list)] == node_list or pangenome.get_path(path).nodes[idx[0]-len(node_list)+1:idx[0]+1] == node_list[::-1]:
                found.append(path)
                
    return found

def get_abundance(reads,variants):
    
    # multimapped reads = reads with more than one alignment
    multi_reads = []
    
    # ambiguous reads = reads with one alignment but matching to more than one gene
    ambig_reads = defaultdict(list)
    
    # if read has no match to the existing colored paths
    nocolor_reads = defaultdict(list) # key=cluster, value=(read,pair)
    
    # loop over reads
    max_c = 0
    d_abund = {}
    for read in reads:
        for pair in reads[read]: # pair == sequence ACGT of the left or right read 
            print(read)
            
            if len(reads[read][pair]) > 1: # multimapped read
                multi_reads.append((read,pair))
                continue
    
            # here reads with only 1 alignment
            align = reads[read][pair][0]
            align_nodes = [n[0] for n in align.nodes]
            found = get_matching_path(align_nodes) # ids of matched paths 
            genes_found = list(set([d_idt[i]['genes'] for i in found])) # converting ids into actual variants (eg;"1-2-3-4")
            
            # new path in the graph
            if len(genes_found) == 0: 
                nocolor_reads[d_idt[list(pangenome.get_node(align_nodes[0]).pathsCrossed.keys())[0]]['cluster']].append( (read,pair) )
                continue
            
            # case of ambiguous read
            if len(genes_found) > 1: 
                for i in genes_found:
                    ambig_reads[i].append((read,pair))
                continue
    
            # case of unique match
            gene = genes_found[0]
            if gene not in d_abund:
                d_abund[gene] = {}
                d_abund[gene]["uniq_count"] = 0
                d_abund[gene]['nodes_abund'] = {}
                d_abund[gene]["nb_subst"] = {}  # key: nb subst (0-7), value = nb reads correspondant à ce nombre de substitutions 
                # abundance initialization, for each node, start at 0 + get path sequence
                path_seq = ""
                for n in gene.split('-'):
                    d_abund[gene]['nodes_abund'][n] = 0
                    path_seq += pangenome.get_node(n).sequence
            # add to unique count
            d_abund[gene]["uniq_count"] += len(pair)/len(path_seq)
            # sum abundance for each node
            for i in align.nodes: #noeud, abundance
                d_abund[gene]['nodes_abund'][i[0]] += i[1]
            # number of substitutions
            c = 0
            for t in align.variants: # t = (id_noeud, position, nucleotide)
                if not isinstance(t[1], str): # si la position n'est pas une string alors c'est une substitution
                    c += 1
                # else insersion - not treated currently
            if c > max_c:
                max_c = c
            if c not in d_abund[gene]['nb_subst']: 
                d_abund[gene]['nb_subst'][c] = 0
            d_abund[gene]['nb_subst'][c] += 1  
    
    # nb of substitutions by nodes
    subst = {} # key = node id, value = nb subst
    for node in variants:
        for pos in variants[node]:
            if "_" not in str(pos):
                if node not in subst:
                    subst[node] = 1
                else:
                    subst[node] += 1
    
    for gene in d_abund:
        
        # sum of substs for each gene
        d_abund[gene]['nb_subst']["total_norm"] = 0
        g_nodes = gene.split("-")
        for n in g_nodes:
            d_abund[gene]['nb_subst']["total_norm"] += subst.get(n,0)
        d_abund[gene]['nb_subst']["total_norm"] /= len(pangenome.get_path(d_genes[gene][0]).sequence)
    
        # for each variant, get coverage, mean abundance and std
        d_abund[gene]['coverage'] = len([i for i in [d_abund[gene]['nodes_abund'][j] for j in d_abund[gene]['nodes_abund']] if i > 0])/len(d_abund[gene]['nodes_abund'])
        d_abund[gene]['mean_abund'] = np.mean([i for i in [d_abund[gene]['nodes_abund'][j] for j in d_abund[gene]['nodes_abund']]])
        d_abund[gene]['std_abund'] = np.std([i for i in [d_abund[gene]['nodes_abund'][j] for j in d_abund[gene]['nodes_abund']]])
    
    
    list_thr = [x/100 for x in range(0,105,5)]
    d_strains_abund = {}
    for v in d_abund:
        cov = d_abund[v]['coverage']
        s = set([g.split("|")[3] for g in d_genes[v]]) # list of strains where the variant is found
        for e in s:
            # initialization
            if e not in d_strains_abund: 
                d_strains_abund[e] = {}            
                for thr in list_thr:
                    d_strains_abund[e][thr] = {}
                    d_strains_abund[e][thr]['nb_genes'] = 0
                    d_strains_abund[e][thr]['abund'] = [] # need list structure to normalize by number of copy afterwards
                    d_strains_abund[e][thr]['nb_copy'] = []
                    d_strains_abund[e][thr]['nb_subst'] = {}
                    d_strains_abund[e][thr]['nb_subst']['total'] = {}
                    d_strains_abund[e][thr]['nb_subst']['uniq'] = {}
            # process
            for thr in list_thr:
                if cov >= thr:
                    d_strains_abund[e][thr]['nb_genes'] += 1
                    d_strains_abund[e][thr]['abund'].append(d_abund[v]['mean_abund'])
                    # nb copy of the variant
                    c = 0
                    for i in d_genes[v]:
                        if i.split("|")[-2] == e: c +=1
                    d_strains_abund[e][thr]['nb_copy'].append(c)
                    # nb of errors
                    for nb in d_abund[v]['nb_subst']:
                        if nb not in d_strains_abund[e][thr]['nb_subst']['total']: d_strains_abund[e][thr]['nb_subst']['total'][nb] = 0
                        if nb not in d_strains_abund[e][thr]['nb_subst']['uniq']: d_strains_abund[e][thr]['nb_subst']['uniq'][nb] = 0
                        d_strains_abund[e][thr]['nb_subst']['total'][nb] += d_abund[v]['nb_subst'][nb]
                        if len(s)==1: d_strains_abund[e][thr]['nb_subst']['uniq'][nb] += d_abund[v]['nb_subst'][nb]
    
    # compute mean and std abundance
    for s in d_strains_abund:
        for thr in d_strains_abund[s]:
            abund_norm = [int(a) / int(b) for a,b in zip(d_strains_abund[s][thr]['abund'], d_strains_abund[s][thr]['nb_copy'])]
            d_strains_abund[s][thr]['std'] = np.std(abund_norm)
            d_strains_abund[s][thr]['abund'] = np.mean(abund_norm)
    
    df = pd.DataFrame(columns=['strains','thr_cov','nb_genes','mean_abund','p_subst']+[f"X{c}" for i in range(0,max_c+1)])
    for s in d_strains_abund:
        for thr in d_strains_abund[s]:
            d_tmp = {}
            d_tmp['strain'] = s
            d_tmp['thr_cov'] = thr
            d_tmp['nb_genes'] = d_strains_abund[s][thr]['nb_genes']
            d_tmp['mean_abund'] = d_strains_abund[s][thr]['abund']
            for i in d_strains_abund[s][thr]['nb_subst']['total']:
                if not isinstance(i, int):
                    d_tmp['p_subst'] = d_strains_abund[s][thr]['nb_subst']['total'][i]
                else:
                    d_tmp['X'+str(i)] = d_strains_abund[s][thr]['nb_subst']['total'][i]
    
            df = df.append(d_tmp, ignore_index=True)
    
    return d_abund, d_strains_abund, df






def get_abundance_old(reads):
    df_nodes = pd.DataFrame(0, index=list(pangenome.nodes.keys()), columns=['abundance'])
    df_edges = pd.DataFrame(0, index=list(pangenome.edges.keys()), columns=['abundance'])
    for read_id in reads:
        for read_seq in reads[read_id]:
            # use only unambiguous reads for now
            if len(reads[read_id][read_seq])==1:
                # nodes abundance
                align = reads[read_id][read_seq][0]
                z1, z2 = zip(*align.nodes)
                df_nodes.loc[z1,"abundance"] += z2
                # edges abundance
                nodes = [n[0] for n in align.nodes]
                for i in range(len(nodes)-1):
                    if (nodes[i],nodes[i+1]) in pangenome.edges.keys():
                        df_edges.loc[[(nodes[i],nodes[i+1])],"abundance"] +=1
                    elif (nodes[i+1],nodes[i]) in pangenome.edges.keys():
                        df_edges.loc[[(nodes[i+1],nodes[i])],"abundance"] +=1
    return df_nodes, df_edges

def get_abundance_old2(reads, multimap=False):
    
    # dico clusters (clusters -> identifiants des variants)
    d_clusters = pickle.load( open( "/home/kdasilva/finalwork_lasso/graphs/dict_clusters.pickle", "rb" ) )
    
    # dico variants (variant -> identifiants)
    d_variants = {}
    for key in pangenome.paths:
        nodelist = '-'.join(pangenome.paths[key].nodes)
        nodelist_r = '-'.join(pangenome.paths[key].nodes[::-1])
        if nodelist in d_variants:
            d_variants[nodelist].append(key)
        elif nodelist_r in d_variants:
            d_variants[nodelist_r].append(key)
        else:
            d_variants[nodelist] = [key]
    print(f'Nombre de variants uniques : {len(d_variants)}')
    
    # dico identifiants (identifiant -> cluster + variant)
    d_idt = defaultdict(dict)
    for i in d_variants:
        for j in d_variants[i]:
            d_idt[j]['variant'] = i
    for i in d_clusters:
        for j in d_clusters[i]['genes_list']:
            d_idt[j]['cluster'] = i
    
    # multimapped reads = reads with more than one alignment
    multi_reads = []
    
    # ambiguous reads = reads with one alignment but matching to more than one gene
    ambig_reads = defaultdict(list)
    
    # if read has no match to the existing colored paths
    nocolor_reads = defaultdict(list) # key=cluster, value=(read,pair)

    # loop over reads
    d_variants_abund = {}
    for read in reads:
        for pair in reads[read]:
            print(read)
            
            if len(reads[read][pair]) > 1: # multimapped read
                multi_reads.append((read,pair))
            else: # reads with only 1 alignment
                align = reads[read][pair][0]
                align_nodes = [n[0] for n in align.nodes]
                found = get_matching_path(align_nodes)
                variants_found = list(set([d_idt[i]['variant'] for i in found]))
            
                if len(variants_found) == 0: # new path in the graph
                    nocolor_reads[d_idt[list(pangenome.nodes[align_nodes[0]].pathsCrossed.keys())[0]]['cluster']].append( (read,pair) )
                elif len(variants_found) > 1: # ambiguous read
                    for i in variants_found:
                        ambig_reads[i].append((read,pair))
                else: # unique match
                    variant = variants_found[0]
                    if variant not in d_variants_abund:
                        d_variants_abund[variant] = {}
                        d_variants_abund[variant]['nodes_abund'] = {}
                        d_variants_abund[variant]["nb_errors"] = {}
                        for i in variant.split('-'):
                            d_variants_abund[variant]['nodes_abund'][i] = 0
                    # sum abundance for each node
                    for i in align.nodes:
                        d_variants_abund[variant]['nodes_abund'][i[0]] += i[1]
                    # number of errors
                    nb_errors = len(align.variations)
                    if nb_errors not in d_variants_abund[variant]["nb_errors"]: d_variants_abund[variant]["nb_errors"][nb_errors] = 0
                    d_variants_abund[variant]["nb_errors"][nb_errors] += 1
        
    # loop over variants
    for variant in d_variants_abund:
        d_variants_abund[variant]['coverage'] = len([i for i in [d_variants_abund[variant]['nodes_abund'][j] for j in d_variants_abund[variant]['nodes_abund']] if i > 0])/len(d_variants_abund[variant]['nodes_abund'])
        d_variants_abund[variant]['mean_abund'] = np.mean([i for i in [d_variants_abund[variant]['nodes_abund'][j] for j in d_variants_abund[variant]['nodes_abund']]])
        d_variants_abund[variant]['std_abund'] = np.std([i for i in [d_variants_abund[variant]['nodes_abund'][j] for j in d_variants_abund[variant]['nodes_abund']]])
    
    return d_variants_abund, multi_reads, ambig_reads, nocolor_reads

# final table
d_final = {}
for v in d_variants_abund:
    cov = d_variants_abund[v]['coverage']
    s = set([g.split("|")[3] for g in d_variants[v]])
    for e in s:
        # initialization
        if e not in d_final: 
            d_final[e] = {}            
            for thr in [0, 0.5, 0.9, 0.95, 1]:
                d_final[e][thr] = {}
                d_final[e][thr]['nb_genes'] = 0
                d_final[e][thr]['abund'] = []
                d_final[e][thr]['nb_copy'] = []
                d_final[e][thr]['nb_errors'] = {}
                d_final[e][thr]['nb_errors']['total'] = {}
                d_final[e][thr]['nb_errors']['uniq'] = {}
        # process
        for thr in [0, 0.5, 0.9, 0.95, 1]:
            if cov >= thr:
                d_final[e][thr]['nb_genes'] += 1
                d_final[e][thr]['abund'].append(d_variants_abund[v]['mean_abund'])
                # nb copy of the variant
                c = 0
                for i in d_variants[v]:
                    if i.split("|")[-2] == e: c +=1
                d_final[e][thr]['nb_copy'].append(c)
                # nb of errors
                for nb in d_variants_abund[v]['nb_errors']:
                    if nb not in d_final[e][thr]['nb_errors']['total']: d_final[e][thr]['nb_errors']['total'][nb] = 0
                    if nb not in d_final[e][thr]['nb_errors']['uniq']: d_final[e][thr]['nb_errors']['uniq'][nb] = 0
                    d_final[e][thr]['nb_errors']['total'][nb] += d_variants_abund[v]['nb_errors'][nb]
                    if len(s)==1: d_final[e][thr]['nb_errors']['uniq'][nb] += d_variants_abund[v]['nb_errors'][nb]

for s in d_final:
    for thr in d_final[s]:
        abund_norm = [int(a) / int(b) for a,b in zip(d_final[s][thr]['abund'], d_final[s][thr]['nb_copy'])]
        d_final[s][thr]['std'] = np.std(abund_norm)
        d_final[s][thr]['abund'] = np.mean(abund_norm)

for s in d_final:
    print(f"{s}")
    for thr in d_final[s]:
        print(f"{d_final[s][thr]['nb_genes']} gènes pour une couverture >= {thr}")
        print(f"abondance moyenne de {d_final[s][thr]['abund']} +/- {d_final[s][thr]['std']}")
        
#################################################
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping from keyboard")