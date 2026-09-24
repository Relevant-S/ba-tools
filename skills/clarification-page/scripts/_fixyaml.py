import io,sys
keys=("detail:","title:","meta:","t:","d:","note:","section:","note_placeholder:","doc_title:","eyebrow:","stages_label:","close_title:","copy_header:","spec:","slug:","product:","store_key:")
for p in sys.argv[1:]:
    L=io.open(p,encoding="utf-8").read().split("\n"); f=0
    for i,line in enumerate(L):
        st=line.strip()
        for k in keys:
            if st.startswith(k):
                val=st[len(k):].strip()
                if not val or val[0] in "|>'\"": break
                if ": " in val or val.endswith(":"):
                    ind=line[:len(line)-len(line.lstrip())]
                    L[i]=ind+k+' "'+val.replace('"','\\"')+'"'; f+=1
                break
    io.open(p,"w",encoding="utf-8").write("\n".join(L))
    print(p,"->",f,"quoted")
